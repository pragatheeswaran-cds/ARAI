"""Audit supplied masters without modifying them or training models."""
from pathlib import Path
from datetime import date, timedelta
from collections import Counter
import ast
import calendar
import contextlib
import hashlib
import io
import json
import re
import zipfile

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'code' / 'synthetic-data'
OUT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell_code(path, number):
    return ''.join(json.loads(path.read_text(encoding='utf-8-sig'))['cells'][number]['source'])


def main():
    customer_path = SRC/'customer-master/output/customer_master.csv'
    sku_path = SRC/'sku-master/sku_master.csv'
    cfg_path = SRC/'customer-master/config/cluster_rules.yaml'
    festive_path = SRC/'customer-master/config/festive_windows.yaml'
    cfg = yaml.safe_load(cfg_path.read_text())
    festive = yaml.safe_load(festive_path.read_text())
    customers = pd.read_csv(customer_path)
    skus = pd.read_csv(sku_path)
    asof = pd.Timestamp(cfg['as_of_date'])
    signup = pd.to_datetime(customers.signup_date)
    fraud = customers.customer_segment.eq('Fraud Proxy')
    zero = customers.actual_orders.eq(0)
    one = customers.actual_orders.eq(1)
    calc_gap = customers.tenure_days / customers.actual_orders.replace(0, np.nan)
    calendar_days = [date(2025,9,10)+timedelta(days=i) for i in range(365)]
    def festive_day(day):
        md = day.strftime('%m-%d')
        return any((w['start'] <= md <= w['end']) if w['start'] <= w['end']
                   else (md >= w['start'] or md <= w['end']) for w in festive['windows'])
    festive_dates = [d for d in calendar_days if festive_day(d)]
    no_festive = signup.dt.date.map(lambda d: not any(day >= d for day in festive_dates))
    impossible_target = no_festive & customers.actual_orders.gt(0) & customers.festive_order_ratio.gt(0)
    cust = {
        'rows': len(customers), 'columns': list(customers.columns),
        'duplicate_ids': int(customers.customer_id.duplicated().sum()),
        'null_counts': {k:int(v) for k,v in customers.isna().sum().items()},
        'segments': {k:int(v) for k,v in customers.customer_segment.value_counts().items()},
        'statuses': {k:int(v) for k,v in customers.account_status.value_counts().items()},
        'signup_range': [str(signup.min().date()),str(signup.max().date())],
        'tenure_mismatches': int(customers.tenure_days.ne((asof-signup).dt.days).sum()),
        'negative_orders': int(customers.actual_orders.lt(0).sum()),
        'invalid_return_ratio': int((~customers.return_rate.between(0,1)).sum()),
        'invalid_festive_ratio': int((~customers.festive_order_ratio.between(0,1)).sum()),
        'zero_order_rows': int(zero.sum()),
        'zero_order_inconsistencies': int((zero & (customers.return_rate.ne(0) | customers.festive_order_ratio.ne(0) | customers.avg_days_between_orders.notna())).sum()),
        'one_order_nonnull_avg_gap': int((one & customers.avg_days_between_orders.notna()).sum()),
        'gap_tenure_div_orders_max_abs_difference': float((customers.avg_days_between_orders-calc_gap).abs().max()),
        'fraud_count': int(fraud.sum()),
        'fraud_active_count': int((fraud & customers.account_status.eq('ACTIVE')).sum()),
        'fraud_flagged_or_suspended_rate': float(customers.loc[fraud,'account_status'].isin(['FLAGGED','SUSPENDED']).mean()),
        'nonfraud_flagged_or_suspended_rate': float(customers.loc[~fraud,'account_status'].isin(['FLAGGED','SUSPENDED']).mean()),
        'fraud_one_device': int((fraud & customers.shared_device_count.eq(1)).sum()),
        'nonfraud_three_plus_devices': int((~fraud & customers.shared_device_count.ge(3)).sum()),
        'nonfraud_return_at_least_032': int((~fraud & customers.return_rate.ge(.32)).sum()),
        'fraud_return_at_most_032': int((fraud & customers.return_rate.le(.32)).sum()),
        'no_festive_day_since_signup_positive_target_count': int(impossible_target.sum()),
        'last_festive_day_in_window': str(max(festive_dates)),
        'no_festive_target_examples': customers.loc[impossible_target,['customer_id','signup_date','actual_orders','festive_order_ratio']].head(5).to_dict('records'),
    }
    sku_spec_path = SRC/'sku-master/sku_master_synthetic_generation_spec_v2.md'
    spec = sku_spec_path.read_text(encoding='utf-8')
    styles = {}
    for line in spec.splitlines():
        parts = [p.strip() for p in line.strip().strip('|').split('|')]
        if len(parts)==7 and re.fullmatch(r'B[A-E]-[A-Z]{3}-\d{2}',parts[0]):
            styles[parts[0]]={'count':int(parts[2]),'colors':set(parts[3].split(', ')),
                              'sizes':set(parts[4].split(', ')),'band':parts[5],'price':int(parts[6])}
    assert len(styles)==37, len(styles)
    fields = ['brand','category','unit_price','price_band','return_window_days','is_occasion_wear','launch_date','active_flag']
    style_mismatches=[]
    category_codes={'TSH':'T-shirt','SHT':'Shirt','JNS':'Jeans','JKT':'Jacket','DRS':'Dress'}
    for sid, group in skus.groupby('style_id'):
        ref=styles[sid]
        expected_brand='Brand_'+sid[1]
        expected_category=category_codes[sid.split('-')[1]]
        if len(group)!=ref['count'] or not set(group.color)<=ref['colors'] or not set(group['size'])<=ref['sizes'] or not group.unit_price.eq(ref['price']).all() or not group.price_band.eq(ref['band']).all() or not group.brand.eq(expected_brand).all() or not group.category.eq(expected_category).all():
            style_mismatches.append(sid)
    style_rows=skus.drop_duplicates('style_id').copy()
    category_rank={'T-shirt':1,'Shirt':2,'Jeans':3,'Jacket':4,'Dress':5}
    ladder_failures=[]
    for (brand,band),group in style_rows.groupby(['brand','price_band']):
        prev=None
        for category in sorted(group.category.unique(),key=category_rank.get):
            prices=group.loc[group.category.eq(category),'unit_price']
            if prev is not None and prev>prices.min(): ladder_failures.append(['category',brand,band,category])
            prev=prices.max()
    for (category,band),group in style_rows.groupby(['category','price_band']):
        prev=None
        for brand in sorted(group.brand.unique()):
            prices=group.loc[group.brand.eq(brand),'unit_price']
            if prev is not None and prev>prices.min(): ladder_failures.append(['brand',category,band,brand])
            prev=prices.max()
    for key,group in style_rows.groupby(['brand','category','price_band']):
        if not group.sort_values('style_id').unit_price.is_monotonic_increasing: ladder_failures.append(['sequence',*key])
    color_map={'Black':'C001','White':'C002','Navy':'C003','Grey':'C004','Red':'C005','Green':'C006','Beige':'C007'}
    policy={'T-shirt':30,'Shirt':30,'Jeans':30,'Jacket':45,'Dress':60}
    launches=pd.to_datetime(skus.launch_date)
    style_lifecycle=skus.groupby('style_id').agg(n=('sku_id','size'),launch=('launch_date','first'),active=('active_flag','first')).sort_values(['launch','style_id'])
    prefix_sums=np.r_[0,style_lifecycle.n.cumsum().to_numpy()]
    closest=prefix_sums[np.abs(prefix_sums-45)==np.abs(prefix_sums-45).min()].tolist()
    actual_inactive=int((~skus.active_flag).sum())
    actual_inactive_styles=set(style_lifecycle.index[~style_lifecycle.active])
    prefix_matches=any(set(style_lifecycle.index[:i])==actual_inactive_styles for i in range(len(style_lifecycle)+1) if int(prefix_sums[i])==actual_inactive)
    expected_occasion_styles={'BB-SHT-03','BD-DRS-02','BD-DRS-03','BE-JKT-02','BE-DRS-01','BE-DRS-02'}
    sku={
        'rows':len(skus),'columns':list(skus.columns),'styles':len(styles),
        'duplicate_ids':int(skus.sku_id.duplicated().sum()),
        'duplicate_variants':int(skus.duplicated(['style_id','color','size']).sum()),
        'null_cells':int(skus.isna().sum().sum()),
        'style_invariant_violations':{f:int((skus.groupby('style_id')[f].nunique(dropna=False)>1).sum()) for f in fields},
        'style_spec_mismatches':style_mismatches,'ladder_failures':ladder_failures,
        'color_id_mismatches':int(skus.color.map(color_map).ne(skus.color_id).sum()),
        'return_policy_mismatches':int(skus.category.map(policy).ne(skus.return_window_days).sum()),
        'charm_price_violations':int(((skus.unit_price%100)!=99).sum()),
        'occasion_count':int(skus.is_occasion_wear.sum()),
        'occasion_style_set_matches':set(skus.loc[skus.is_occasion_wear,'style_id'])==expected_occasion_styles,
        'inactive_count':actual_inactive,'nearest_whole_style_retirement_prefix_totals':closest,
        'inactive_is_oldest_prefix':prefix_matches,
        'launch_range':[str(launches.min().date()),str(launches.max().date())],
        'launched_after_history_start_rows':int((launches>pd.Timestamp('2025-09-10')).sum()),
        'price_range':[int(skus.unit_price.min()),int(skus.unit_price.max())],
        'band_counts':{k:int(v) for k,v in skus.price_band.value_counts().items()},
    }
    source_presence={name:[str(p.relative_to(ROOT)) for p in ROOT.rglob(name)] for name in ['sku_config_v2.py','sku_generator_v2.py']}
    archive_presence={}
    for archive in ROOT.glob('*.zip'):
        with zipfile.ZipFile(archive) as z:
            archive_presence[archive.name]=[n for n in z.namelist() if any(term in n.lower() for term in ['sku_config_v2.py','sku_generator_v2.py','customer_generator','generate_customer'])]
    # Execute only the notebook's small diagnostic branch, not a clustering fit.
    db_path=SRC/'customer-master/notebooks/dbscan_clustering.ipynb'
    tree=ast.parse(cell_code(db_path,13))
    branch=[n for n in tree.body if isinstance(n,ast.If)][-1]
    out=io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(ast.Module(body=[branch],type_ignores=[]),str(db_path)+'::cell13-final-branch','exec'),{'n_noise':300,'noise_pct':30,'fraud_n':200,'fraud_noise':40})
    diagnostic={'population':1000,'fraud_n':200,'noise_n':300,'fraud_noise':40,
                'recall':.20,'noise_fraud_share':40/300,'population_fraud_share':.20,
                'enrichment_ratio':(40/300)/.20,'actual_notebook_branch_output':out.getvalue().strip()}
    # Exercise the actual date validation cell with an invalid in-memory copy.
    eda=SRC/'customer-master/notebooks/customer_master_eda.ipynb'
    invalid=customers.copy(); invalid.loc[0,'tenure_days']=-1
    out=io.StringIO(); raised=None
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(cell_code(eda,7),str(eda)+'::cell7','exec'),{'df':invalid,'pd':pd,'AS_OF':asof,'calendar':calendar,'display':lambda value:None})
    except Exception as exc: raised=type(exc).__name__+': '+str(exc)
    validator={'injected':'negative tenure in first in-memory row','printed_fail':'RESULT: FAIL' in out.getvalue(),'raised_exception':raised}
    files=[customer_path,sku_path,cfg_path,festive_path,sku_spec_path]
    result={'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in files},'customer':cust,'sku':sku,
            'helper_source_presence':source_presence,'archive_helper_presence':archive_presence,
            'diagnostic_reproduction':diagnostic,'validator_reproduction':validator,
            'not_run':['full notebooks','source generator','new synthetic dataset','model training','parquet parity (pyarrow absent)']}
    (OUT/'data-audit.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    print(json.dumps(result,indent=2,default=str))


if __name__=='__main__': main()
