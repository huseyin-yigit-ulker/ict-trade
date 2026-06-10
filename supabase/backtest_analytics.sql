create schema if not exists ict_trade;

-- All four analytics functions take p_version (default 'v1') so each backtest
-- stream is aggregated SEPARATELY. The old no-arg versions are dropped first
-- because adding a parameter creates a NEW signature — leaving the no-arg ones
-- in place would make PostgREST's rpc/* resolution ambiguous on an empty body.
drop function if exists ict_trade.backtest_summary_metrics();
drop function if exists ict_trade.backtest_symbol_metrics();
drop function if exists ict_trade.backtest_weekday_metrics();
drop function if exists ict_trade.backtest_session_metrics();

create or replace function ict_trade.backtest_summary_metrics(p_version text default 'v1')
returns table (
  total_trades bigint,
  closed_trades bigint,
  tp_count bigint,
  sl_count bigint,
  cancelled_count bigint,
  win_rate numeric,
  total_r numeric,
  avg_r numeric,
  expectancy_r numeric,
  profit_factor numeric,
  avg_minutes numeric
)
language sql
stable
as $$
with base as (
  select
    lower(coalesce(status, '')) as s,
    coalesce(pnl_r, 0)::numeric as r,
    extract(epoch from (coalesce(exit_time, signal_time) - coalesce(real_entry_time, signal_time))) / 60.0 as dur_min
  from ict_trade.trading_signals
  where version = p_version
),
closed as (
  select * from base where s in ('closed_tp', 'closed_sl')
)
select
  (select count(*) from base) as total_trades,
  count(*) as closed_trades,
  count(*) filter (where s = 'closed_tp') as tp_count,
  count(*) filter (where s = 'closed_sl') as sl_count,
  (select count(*) from base where s in ('cancelled', 'canceled')) as cancelled_count,
  round((count(*) filter (where s = 'closed_tp')::numeric / nullif(count(*), 0)) * 100, 2) as win_rate,
  round(coalesce(sum(r), 0), 4) as total_r,
  round(coalesce(avg(r), 0), 4) as avg_r,
  round(coalesce(avg(r), 0), 4) as expectancy_r,
  round(
    coalesce(sum(case when r > 0 then r else 0 end), 0)
    / nullif(abs(sum(case when r < 0 then r else 0 end)), 0),
    4
  ) as profit_factor,
  round(coalesce(avg(dur_min), 0), 2) as avg_minutes
from closed;
$$;

create or replace function ict_trade.backtest_symbol_metrics(p_version text default 'v1')
returns table (
  symbol text,
  total_trades bigint,
  tp_count bigint,
  sl_count bigint,
  win_rate numeric,
  total_r numeric,
  avg_r numeric,
  profit_factor numeric,
  expectancy_r numeric
)
language sql
stable
as $$
with closed as (
  select
    symbol,
    lower(coalesce(status, '')) as s,
    coalesce(pnl_r, 0)::numeric as r
  from ict_trade.trading_signals
  where version = p_version
    and lower(coalesce(status, '')) in ('closed_tp', 'closed_sl')
)
select
  symbol,
  count(*) as total_trades,
  count(*) filter (where s = 'closed_tp') as tp_count,
  count(*) filter (where s = 'closed_sl') as sl_count,
  round((count(*) filter (where s = 'closed_tp')::numeric / nullif(count(*), 0)) * 100, 2) as win_rate,
  round(coalesce(sum(r), 0), 4) as total_r,
  round(coalesce(avg(r), 0), 4) as avg_r,
  round(
    coalesce(sum(case when r > 0 then r else 0 end), 0)
    / nullif(abs(sum(case when r < 0 then r else 0 end)), 0),
    4
  ) as profit_factor,
  round(coalesce(avg(r), 0), 4) as expectancy_r
from closed
group by symbol
order by total_r desc, win_rate desc;
$$;

create or replace function ict_trade.backtest_weekday_metrics(p_version text default 'v1')
returns table (
  weekday_no int,
  weekday_name text,
  total_trades bigint,
  win_rate numeric,
  total_r numeric,
  avg_r numeric
)
language sql
stable
as $$
with closed as (
  select
    extract(isodow from signal_time)::int as wd,
    lower(coalesce(status, '')) as s,
    coalesce(pnl_r, 0)::numeric as r
  from ict_trade.trading_signals
  where version = p_version
    and lower(coalesce(status, '')) in ('closed_tp', 'closed_sl')
)
select
  wd as weekday_no,
  case wd
    when 1 then 'Pazartesi'
    when 2 then 'Sali'
    when 3 then 'Carsamba'
    when 4 then 'Persembe'
    when 5 then 'Cuma'
    when 6 then 'Cumartesi'
    when 7 then 'Pazar'
  end as weekday_name,
  count(*) as total_trades,
  round((count(*) filter (where s = 'closed_tp')::numeric / nullif(count(*), 0)) * 100, 2) as win_rate,
  round(coalesce(sum(r), 0), 4) as total_r,
  round(coalesce(avg(r), 0), 4) as avg_r
from closed
group by wd
order by wd;
$$;

create or replace function ict_trade.backtest_session_metrics(p_version text default 'v1')
returns table (
  session_name text,
  total_trades bigint,
  win_rate numeric,
  total_r numeric,
  avg_r numeric
)
language sql
stable
as $$
with closed as (
  select
    case
      when extract(hour from signal_time at time zone 'UTC') between 0 and 7 then 'Asia'
      when extract(hour from signal_time at time zone 'UTC') between 8 and 15 then 'Europe'
      else 'US'
    end as session_name,
    lower(coalesce(status, '')) as s,
    coalesce(pnl_r, 0)::numeric as r
  from ict_trade.trading_signals
  where version = p_version
    and lower(coalesce(status, '')) in ('closed_tp', 'closed_sl')
)
select
  session_name,
  count(*) as total_trades,
  round((count(*) filter (where s = 'closed_tp')::numeric / nullif(count(*), 0)) * 100, 2) as win_rate,
  round(coalesce(sum(r), 0), 4) as total_r,
  round(coalesce(avg(r), 0), 4) as avg_r
from closed
group by session_name
order by total_r desc;
$$;

grant usage on schema ict_trade to anon, authenticated;
grant execute on function ict_trade.backtest_summary_metrics(text) to anon, authenticated;
grant execute on function ict_trade.backtest_symbol_metrics(text) to anon, authenticated;
grant execute on function ict_trade.backtest_weekday_metrics(text) to anon, authenticated;
grant execute on function ict_trade.backtest_session_metrics(text) to anon, authenticated;
