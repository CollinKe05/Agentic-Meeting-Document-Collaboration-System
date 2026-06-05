#!/bin/bash
# syss 文档处理系统启动脚本 (RDK X5 / Linux)
# 用法:
#   ./run.sh benchmark          # 各环节耗时测试
#   ./run.sh pipeline demo.pdf  # 完整流水线
#   ./run.sh layout demo.pdf    # 仅版面分析

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/..:$PYTHONPATH"

CMD=${1:-benchmark}
shift 2>/dev/null

case "$CMD" in
    benchmark)
        python3 "$SCRIPT_DIR/benchmark.py" "$@"
        ;;
    pipeline)
        python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR/..')
from syss.main import main
main()
" pipeline "$@"
        ;;
    *)
        echo "Usage: $0 {benchmark|pipeline|layout|ocr|llm} [args...]"
        exit 1
        ;;
esac
