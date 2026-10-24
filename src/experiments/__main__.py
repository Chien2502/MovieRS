"""CLI: python -m src.experiments prepare|run --profile research."""

import argparse
import os
import sys

from src.experiments.config import ROOT, load_config


def main(argv=None):
    parser=argparse.ArgumentParser(description='MovieRS: quy trình nghiên cứu tái lập')
    parser.add_argument('command',choices=['prepare','run'])
    parser.add_argument('--config',default=str(ROOT/'configs/research.toml'))
    parser.add_argument('--profile',default='research')
    parser.add_argument('--resume',default=None)
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    config=load_config(args.config)
    if args.profile not in config.profiles:
        parser.error('Profile không có trong cấu hình')
    if not args.worker:
        from src.experiments.resources import supervise
        forwarded=list(argv if argv is not None else sys.argv[1:])
        return supervise([sys.executable,'-m','src.experiments',*forwarded,'--worker'],config,args.profile)
    # Đặt trước khi import NumPy/SciPy để BLAS không chiếm toàn bộ CPU.
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
        os.environ[name]=str(config.resources.threads)
    from src.data.snapshots import prepare_snapshot
    from src.experiments.resources import ResourceMonitor
    with ResourceMonitor(config.resources,config.profiles[args.profile].minutes) as monitor:
        snapshot=prepare_snapshot(config,args.profile,monitor.check)
    print('Snapshot:',snapshot,flush=True)
    if args.command=='run':
        from src.experiments.runner import run_experiment
        print('Run:',run_experiment(config,snapshot,args.profile,args.resume),flush=True)
    return 0


if __name__=='__main__':
    sys.exit(main())
