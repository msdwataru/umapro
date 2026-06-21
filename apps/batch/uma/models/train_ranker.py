"""
LightGBM Ranker 学習スクリプト。

特徴量 parquet を読み込み、レース内着順ランキングを rank_xendcg で学習する。
- 学習ターゲット: (field_size + 1 - finish_position) / field_size  → [0, 1]
- 時系列分割: val_from_date より前を訓練、以降を検証
- 評価: win_acc / top3_acc / ndcg@1 / ndcg@3
- モデル保存: artifacts/lgbm_ranker_v1.txt
- DB登録: model_versions テーブルに upsert、job_runs に記録

Usage:
    cd apps/batch
    python -m uma.models.train_ranker
    python -m uma.models.train_ranker --val-from 20260601 --n-estimators 1000
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import ndcg_score

from uma.db.client import get_client
from uma.jobs.base import job_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── パス定数 ────────────────────────────────────────────────────────
_ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts"
_PARQUET_PATH  = _ARTIFACTS_DIR / "race_features_v1.parquet"
_MODEL_PATH    = _ARTIFACTS_DIR / "lgbm_ranker_v1.txt"

_MODEL_NAME    = "lgbm_ranker"
_MODEL_VERSION = "v1"
_MODEL_TYPE    = "ranker"

# ── 除外カラム ────────────────────────────────────────────────────────
_EXCLUDE_COLS = {
    "race_entry_id", "race_id", "race_date",
    "finish_position", "finish_time_sec",
    "jockey_affiliation_enc",   # 全件 -1（騎手所属データなし）
}

# カテゴリ特徴量（LightGBM に category として渡す）
_CAT_COLS = ["sire_name", "dam_name"]

# ── デフォルトハイパーパラメータ ─────────────────────────────────────
_DEFAULT_PARAMS = dict(
    objective       = "rank_xendcg",
    metric          = "rmse",
    learning_rate   = 0.05,
    num_leaves      = 63,
    min_child_samples = 5,
    subsample       = 0.8,
    colsample_bytree = 0.8,
    reg_alpha       = 0.1,
    reg_lambda      = 0.1,
    random_state    = 42,
    n_jobs          = -1,
    verbose         = -1,
)


# ── データ準備 ───────────────────────────────────────────────────────

def _load_and_prep(parquet_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    # ラベルなし行を除外（予測用エントリは学習に使わない）
    df = df[df["finish_position"].notna()].copy()
    # race_id・race_date でソート（グループ配列作成のため必須）
    df = df.sort_values(["race_date", "race_id", "finish_position"]).reset_index(drop=True)
    logger.info("Loaded: %d rows × %d cols", len(df), len(df.columns))
    return df


def _make_target(df: pd.DataFrame) -> pd.Series:
    """(field_size + 1 - finish_position) / field_size → [0, 1]"""
    return (df["field_size"] + 1 - df["finish_position"]) / df["field_size"]


def _make_groups(df: pd.DataFrame) -> np.ndarray:
    """race_id ごとの頭数配列を返す。df は race_id でソート済みであること。"""
    return df.groupby("race_id", sort=False)["race_id"].transform("count").groupby(
        df["race_id"], sort=False
    ).first().values
    # ↑ 上の書き方は意図が分かりにくいため、シンプルに:


def _group_sizes(df: pd.DataFrame) -> np.ndarray:
    return df.groupby("race_id", sort=False).size().values


def _feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in _EXCLUDE_COLS]


def _encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """sire_name / dam_name を category dtype に変換。"""
    for col in _CAT_COLS:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


# ── 評価 ─────────────────────────────────────────────────────────────

def _evaluate(df_val: pd.DataFrame, scores: np.ndarray, feature_cols: list[str]) -> dict:
    """
    レース単位で評価指標を計算する。

    Returns:
        win_acc   : 予測 rank-1 が実際の 1 着の割合
        top3_acc  : 実際の 1 着が予測 top-3 に入る割合
        ndcg_at_1 : レース平均 NDCG@1
        ndcg_at_3 : レース平均 NDCG@3
        n_races   : 評価レース数
    """
    df_val = df_val.copy()
    df_val["_score"] = scores
    df_val["_target"] = _make_target(df_val)

    win_hits, top3_hits, ndcg1_list, ndcg3_list = [], [], [], []

    for _, grp in df_val.groupby("race_id", sort=False):
        if len(grp) < 2:
            continue
        sc   = grp["_score"].values
        tgt  = grp["_target"].values
        pos  = grp["finish_position"].values

        pred_rank = len(sc) - sc.argsort().argsort()   # 高スコア = 小ランク
        win_hits.append(int(pos[pred_rank.argmin()] == 1))

        top3_pred = set(np.argsort(sc)[::-1][:3])
        top3_hits.append(int(any(pos[i] == 1 for i in top3_pred)))

        # ndcg_score は (1, n) 形式
        ndcg1_list.append(float(ndcg_score([tgt], [sc], k=1)))
        ndcg3_list.append(float(ndcg_score([tgt], [sc], k=3)))

    return {
        "win_acc":   float(np.mean(win_hits))   if win_hits   else 0.0,
        "top3_acc":  float(np.mean(top3_hits))  if top3_hits  else 0.0,
        "ndcg_at_1": float(np.mean(ndcg1_list)) if ndcg1_list else 0.0,
        "ndcg_at_3": float(np.mean(ndcg3_list)) if ndcg3_list else 0.0,
        "n_races":   len(ndcg1_list),
    }


# ── DB登録 ───────────────────────────────────────────────────────────

def _upsert_model_version(
    client,
    feature_set_id: int,
    train_start: str,
    train_end: str,
    metrics: dict,
    artifact_path: str,
) -> int:
    result = (
        client.table("model_versions")
        .upsert(
            {
                "model_name":             _MODEL_NAME,
                "version":                _MODEL_VERSION,
                "model_type":             _MODEL_TYPE,
                "feature_set_id":         feature_set_id,
                "training_period_start":  train_start,
                "training_period_end":    train_end,
                "metrics_json":           metrics,
                "artifact_path":          artifact_path,
                "is_production":          True,
            },
            on_conflict="model_name,version",
        )
        .execute()
    )
    return result.data[0]["id"]


def _get_feature_set_id(client, feature_set_name: str = "lgbm_ranker_v1", version: str = "v1") -> int:
    result = (
        client.table("feature_sets")
        .select("id")
        .eq("feature_set_name", feature_set_name)
        .eq("version", version)
        .single()
        .execute()
    )
    return result.data["id"]


# ── メイン ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LightGBM Ranker 学習")
    parser.add_argument(
        "--val-from", default="20260601", metavar="YYYYMMDD",
        help="検証期間の開始日（それより前が訓練データ）",
    )
    parser.add_argument(
        "--parquet", default=str(_PARQUET_PATH),
        help="特徴量 parquet のパス",
    )
    parser.add_argument("--n-estimators", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--early-stopping", type=int, default=50,
                        help="Early stopping rounds (0 で無効)")
    args = parser.parse_args()

    val_from = datetime.strptime(args.val_from, "%Y%m%d").strftime("%Y-%m-%d")

    client = get_client()

    with job_context("train_lgbm_ranker", "train") as ctx:
        # ── データロード ────────────────────────────────────────────
        df = _load_and_prep(Path(args.parquet))
        df = _encode_categoricals(df)

        feat_cols = _feature_cols(df)
        logger.info("Feature cols: %d  (cat: %s)", len(feat_cols),
                    [c for c in _CAT_COLS if c in feat_cols])

        # ── 時系列分割 ──────────────────────────────────────────────
        train_mask = df["race_date"] < val_from
        val_mask   = df["race_date"] >= val_from

        df_train = df[train_mask].copy()
        df_val   = df[val_mask].copy()

        logger.info(
            "Split: train=%d rows (%d races) / val=%d rows (%d races)",
            len(df_train), df_train["race_id"].nunique(),
            len(df_val),   df_val["race_id"].nunique(),
        )

        if len(df_train) == 0:
            raise ValueError("訓練データが0件です。--val-from の日付を確認してください。")

        X_train = df_train[feat_cols]
        y_train = _make_target(df_train).values
        g_train = _group_sizes(df_train)

        # ── モデル学習 ──────────────────────────────────────────────
        params = {**_DEFAULT_PARAMS, "n_estimators": args.n_estimators,
                  "learning_rate": args.learning_rate}
        ranker = lgb.LGBMRanker(**params)

        callbacks = [lgb.log_evaluation(50)]
        fit_kwargs: dict = {
            "group": g_train,
            "categorical_feature": [c for c in _CAT_COLS if c in feat_cols],
            "callbacks": callbacks,
        }

        if len(df_val) > 0 and args.early_stopping > 0:
            X_val  = df_val[feat_cols]
            y_val  = _make_target(df_val).values
            g_val  = _group_sizes(df_val)
            fit_kwargs["eval_set"]   = [(X_val, y_val)]
            fit_kwargs["eval_group"] = [g_val]
            callbacks.append(lgb.early_stopping(args.early_stopping, verbose=True))
        else:
            X_val, y_val, g_val = None, None, None

        logger.info("Training LightGBM Ranker (n_estimators=%d)...", args.n_estimators)
        ranker.fit(X_train, y_train, **fit_kwargs)

        best_iter = ranker.best_iteration_ or args.n_estimators
        logger.info("Training done. best_iteration=%d", best_iter)

        # ── モデル保存 ──────────────────────────────────────────────
        _ARTIFACTS_DIR.mkdir(exist_ok=True)
        ranker.booster_.save_model(str(_MODEL_PATH))
        logger.info("Model saved: %s", _MODEL_PATH)

        # ── 評価 ────────────────────────────────────────────────────
        train_scores = ranker.predict(X_train)
        train_metrics = _evaluate(df_train, train_scores, feat_cols)
        logger.info("Train metrics: %s", train_metrics)

        val_metrics: dict = {}
        if X_val is not None:
            val_scores  = ranker.predict(X_val)
            val_metrics = _evaluate(df_val, val_scores, feat_cols)
            logger.info("Val metrics:   %s", val_metrics)

        # ── 特徴量重要度 top-20 ──────────────────────────────────────
        fi = pd.Series(
            ranker.feature_importances_,
            index=feat_cols,
        ).sort_values(ascending=False)
        logger.info("Feature importance top-20:\n%s", fi.head(20).to_string())

        # ── DB 登録 ─────────────────────────────────────────────────
        feature_set_id = _get_feature_set_id(client)

        train_start = df_train["race_date"].min()
        train_end   = df_train["race_date"].max()

        metrics_json = {
            "best_iteration": best_iter,
            "n_train_rows":   int(len(df_train)),
            "n_val_rows":     int(len(df_val)),
            "n_features":     len(feat_cols),
            "val_from":       val_from,
            "train": {k: round(v, 4) for k, v in train_metrics.items()},
            "val":   {k: round(v, 4) for k, v in val_metrics.items()} if val_metrics else {},
            "feature_importance_top20": fi.head(20).to_dict(),
        }

        mv_id = _upsert_model_version(
            client,
            feature_set_id = feature_set_id,
            train_start    = train_start,
            train_end      = train_end,
            metrics        = metrics_json,
            artifact_path  = str(_MODEL_PATH),
        )
        logger.info("model_versions 登録完了: id=%d", mv_id)

        ctx["records_processed"] = len(df_train) + len(df_val)

    # ── 最終レポート ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("LightGBM Ranker 学習完了")
    print(f"  モデルパス  : {_MODEL_PATH}")
    print(f"  best_iter   : {best_iter}")
    print(f"  訓練データ  : {len(df_train):,} 行 / {df_train['race_id'].nunique():,} レース")
    if val_metrics:
        print(f"  検証データ  : {len(df_val):,} 行 / {df_val['race_id'].nunique():,} レース")
        print(f"\n  【検証スコア】")
        print(f"    win_acc   : {val_metrics['win_acc']:.3f}  (1着的中率)")
        print(f"    top3_acc  : {val_metrics['top3_acc']:.3f}  (1着がtop3に入る率)")
        print(f"    ndcg@1    : {val_metrics['ndcg_at_1']:.4f}")
        print(f"    ndcg@3    : {val_metrics['ndcg_at_3']:.4f}")
    print(f"\n  【特徴量重要度 top-10】")
    for name, score in fi.head(10).items():
        print(f"    {name:<40} {score:>6.0f}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
