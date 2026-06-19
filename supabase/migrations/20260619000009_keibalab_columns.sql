-- ============================================================
-- 9. 競馬ラボ取込み用カラム追加
-- ============================================================

-- races: 重量条件・本賞金
ALTER TABLE races ADD COLUMN IF NOT EXISTS weight_type varchar(20);   -- 定量/ハンデ/馬齢/別定
ALTER TABLE races ADD COLUMN IF NOT EXISTS prize_money_1st integer;   -- 1着本賞金(万円)

-- jockeys: 所属
ALTER TABLE jockeys ADD COLUMN IF NOT EXISTS affiliation varchar(10); -- 美/栗/地/外

-- trainers: 所属
ALTER TABLE trainers ADD COLUMN IF NOT EXISTS affiliation varchar(10); -- 美/栗/地
