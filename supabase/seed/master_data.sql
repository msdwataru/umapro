-- ============================================================
-- シードデータ: マスタ初期値
-- ============================================================

-- 券種マスタ（MVP対象: 単勝・複勝・ワイド）
insert into bet_types (code, name, is_mvp_target) values
  ('WIN',   '単勝',   true),
  ('PLACE', '複勝',   true),
  ('WIDE',  'ワイド', true),
  ('QUINELLA', '馬連', false),
  ('EXACTA', '馬単',  false),
  ('TRIO',  '三連複', false),
  ('TRIFECTA', '三連単', false)
on conflict (code) do nothing;

-- JRA 競馬場マスタ
insert into racecourses (external_racecourse_code, name, short_name, region, is_active) values
  ('01', '札幌', '札幌', '北海道', true),
  ('02', '函館', '函館', '北海道', true),
  ('03', '福島', '福島', '東北',   true),
  ('04', '新潟', '新潟', '信越',   true),
  ('05', '東京', '東京', '関東',   true),
  ('06', '中山', '中山', '関東',   true),
  ('07', '中京', '中京', '東海',   true),
  ('08', '京都', '京都', '近畿',   true),
  ('09', '阪神', '阪神', '近畿',   true),
  ('10', '小倉', '小倉', '九州',   true)
on conflict (external_racecourse_code) do nothing;
