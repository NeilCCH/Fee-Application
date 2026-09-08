-- 公勝保險 差旅／費用報帳 APP — 草稿資料表
-- 貼到 Supabase 專案的 SQL Editor 執行即可。表名皆加 feeapp_ 前綴，
-- 不會跟同一個 Supabase 專案裡其他應用程式（例如 Tour Planning 原本的表）互相干擾，
-- 之後要搬到獨立專案，只要把這幾張表匯出、在新專案重跑這份 SQL 再匯入資料即可。

create extension if not exists pgcrypto;

-- 出差明細：一趟（一列）＝一筆草稿
create table if not exists feeapp_trip_legs (
  id uuid primary key default gen_random_uuid(),
  owner_name text not null,           -- 填表人姓名，用來簡單過濾「我的草稿」
  date_from text,                     -- 日期起，如 "9/1"
  date_to text,                       -- 日期迄，如 "9/2"
  loc_from text,                      -- 地點起
  loc_to text,                        -- 地點迄
  amounts jsonb not null default '{}'::jsonb,
  -- amounts 範例：{"自用車油":450,"自用車通行":60,"住宿費":2000,"膳雜費":600}
  -- key 只會是這十種之一：火車高鐵/計程車/自用車油/自用車通行/飛機/交通其他/住宿費/膳雜費/交際費/其他
  note text,                          -- 該趟摘要
  created_at timestamptz not null default now()
);

-- 一般費用項次：交際費／文康費／雜支…每筆活動＝一筆草稿
create table if not exists feeapp_expense_items (
  id uuid primary key default gen_random_uuid(),
  owner_name text not null,
  category text not null,             -- 交際費/文康費/雜支/其他
  item_date text,                     -- 選填，如 "9/3"
  description text not null default '',
  amount numeric not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists idx_feeapp_trip_legs_owner on feeapp_trip_legs (owner_name);
create index if not exists idx_feeapp_expense_items_owner on feeapp_expense_items (owner_name);
