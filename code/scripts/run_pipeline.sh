#!/bin/bash
# TraceBench 生成 Pipeline 自动化脚本
# Usage: ./scripts/run_pipeline.sh [INPUT_FILE] [MIN_DEPTH] [OUTPUT_DIR]
#
# IMPORTANT: invoke from the `code/` directory (the parent of scripts/), e.g.:
#   cd code/ && bash scripts/run_pipeline.sh data/datav3.json 3
# generate_solutions.py and the generate-data CLI are resolved relative to that cwd.
#
# Provenance notes (2026-05-15 consolidation):
#   - Step 7 used to call a top-level `generate_tracebench.py` which never
#     existed as a standalone CLI in this repo. The actual dataset generator
#     is `src/cli/generate_data.py`, wrapping `src.core.tracebench_generator
#     .TraceBenchGenerator`. The Step 7 invocation below has been migrated
#     to that interface. The `tbgen/` pipeline (scripts/build_tracebench.py)
#     is an alternative ICML-era path and is NOT used here.

set -e  # 遇到错误立即退出
set -o pipefail  # 管道中任何命令失败都会导致整个管道失败

# 默认参数
INPUT=${1:-data/datav3.json}
MIN_DEPTH=${2:-3}
OUTPUT_DIR=${3:-output/$(date +%Y%m%d_%H%M%S)}

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查依赖
check_dependencies() {
    log_info "检查依赖..."

    if ! command -v python3 &> /dev/null; then
        log_error "python3 未安装"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_warning "jq 未安装，将使用 Python 替代"
        USE_JQ=false
    else
        USE_JQ=true
    fi

    log_success "依赖检查完成"
}

# 获取 JSON 数组长度
json_length() {
    local file=$1
    if [ "$USE_JQ" = true ]; then
        jq 'length' "$file"
    else
        python3 -c "import json; print(len(json.load(open('$file'))))"
    fi
}

# 合并 JSON 数组并去重
json_merge_unique() {
    local file1=$1
    local file2=$2
    local output=$3

    if [ "$USE_JQ" = true ]; then
        jq -s 'add | unique_by(.["problem-id"])' "$file1" "$file2" > "$output"
    else
        python3 -c "
import json
d1 = json.load(open('$file1'))
d2 = json.load(open('$file2'))
merged = d1 + d2
unique = []
seen = set()
for item in merged:
    pid = item.get('problem-id')
    if pid not in seen:
        seen.add(pid)
        unique.append(item)
json.dump(unique, open('$output', 'w'), indent=2, ensure_ascii=False)
"
    fi
}

# 主流程
main() {
    log_info "================================================"
    log_info "TraceBench Pipeline 开始运行"
    log_info "================================================"
    log_info "输入文件: $INPUT"
    log_info "最小深度: $MIN_DEPTH"
    log_info "输出目录: $OUTPUT_DIR"
    log_info ""

    # 检查依赖
    check_dependencies

    # 创建输出目录
    mkdir -p "$OUTPUT_DIR"

    # 保存配置
    cat > "$OUTPUT_DIR/config.json" <<EOF
{
  "input_file": "$INPUT",
  "min_depth": $MIN_DEPTH,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "pipeline_version": "1.0"
}
EOF

    # ========================================
    # Step 1: 过滤深度
    # ========================================
    log_info "Step 1/7: 过滤 depth >= $MIN_DEPTH 的问题"

    if [ -f "scripts/filter_by_depth.py" ]; then
        FILTER_SCRIPT="scripts/filter_by_depth.py"
    elif [ -f "scripts/filter_depth4plus.py" ]; then
        FILTER_SCRIPT="scripts/filter_depth4plus.py"
        log_warning "使用旧版本脚本 filter_depth4plus.py"
    else
        log_error "找不到深度过滤脚本"
        exit 1
    fi

    python3 "$FILTER_SCRIPT" \
        --input "$INPUT" \
        --output "$OUTPUT_DIR/depth${MIN_DEPTH}_filtered.json" \
        --min-depth $MIN_DEPTH \
        2>&1 | tee "$OUTPUT_DIR/step1_filter.log"

    FILTERED_COUNT=$(json_length "$OUTPUT_DIR/depth${MIN_DEPTH}_filtered.json")
    log_success "过滤完成，得到 $FILTERED_COUNT 个问题"

    if [ "$FILTERED_COUNT" -eq 0 ]; then
        log_error "没有符合条件的问题，终止运行"
        exit 1
    fi

    # ========================================
    # Step 2: 第一轮生成（Primary Provider）
    # ========================================
    log_info "Step 2/7: 使用主要模型生成解决方案"

    python3 generate_solutions.py \
        -i "$OUTPUT_DIR/depth${MIN_DEPTH}_filtered.json" \
        -o "$OUTPUT_DIR/solutions_primary.json" \
        --provider together \
        --model "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8" \
        --retries 3 \
        2>&1 | tee "$OUTPUT_DIR/step2_generate_primary.log"

    log_success "主要模型生成完成"

    # ========================================
    # Step 3: 过滤通过的解决方案
    # ========================================
    log_info "Step 3/7: 使用 Harness 验证解决方案"

    python3 scripts/filter_solved.py \
        --solutions "$OUTPUT_DIR/solutions_primary.json" \
        --original "$OUTPUT_DIR/depth${MIN_DEPTH}_filtered.json" \
        --out-solved "$OUTPUT_DIR/solved_primary.json" \
        --out-original "$OUTPUT_DIR/solved_original_primary.json" \
        --out-unsolved "$OUTPUT_DIR/unsolved_primary.json" \
        --out-unsolved-original "$OUTPUT_DIR/unsolved_original_primary.json" \
        2>&1 | tee "$OUTPUT_DIR/step3_filter_primary.log"

    SOLVED_PRIMARY=$(json_length "$OUTPUT_DIR/solved_primary.json")
    UNSOLVED_PRIMARY=$(json_length "$OUTPUT_DIR/unsolved_primary.json")
    PRIMARY_RATE=$(python3 -c "print(f'{$SOLVED_PRIMARY * 100 / $FILTERED_COUNT:.1f}')")

    log_success "主要模型成功率: $SOLVED_PRIMARY/$FILTERED_COUNT ($PRIMARY_RATE%)"

    # ========================================
    # Step 4: 补救生成（Fallback Provider）
    # ========================================
    if [ "$UNSOLVED_PRIMARY" -gt 0 ]; then
        log_info "Step 4/7: 使用备用模型处理 $UNSOLVED_PRIMARY 个失败问题"

        python3 generate_solutions.py \
            -i "$OUTPUT_DIR/unsolved_original_primary.json" \
            -o "$OUTPUT_DIR/solutions_fallback.json" \
            --provider openai \
            --model "gpt-4.1-mini" \
            --retries 3 \
            2>&1 | tee "$OUTPUT_DIR/step4_generate_fallback.log"

        log_success "备用模型生成完成"

        # ========================================
        # Step 5: 再次过滤
        # ========================================
        log_info "Step 5/7: 验证备用模型的解决方案"

        python3 scripts/filter_solved.py \
            --solutions "$OUTPUT_DIR/solutions_fallback.json" \
            --original "$OUTPUT_DIR/unsolved_original_primary.json" \
            --out-solved "$OUTPUT_DIR/solved_fallback.json" \
            --out-original "$OUTPUT_DIR/solved_original_fallback.json" \
            --out-unsolved "$OUTPUT_DIR/unsolved_final.json" \
            --out-unsolved-original "$OUTPUT_DIR/unsolved_original_final.json" \
            2>&1 | tee "$OUTPUT_DIR/step5_filter_fallback.log"

        SOLVED_FALLBACK=$(json_length "$OUTPUT_DIR/solved_fallback.json")
        UNSOLVED_FINAL=$(json_length "$OUTPUT_DIR/unsolved_final.json")

        log_success "备用模型成功: $SOLVED_FALLBACK/$UNSOLVED_PRIMARY"

        # ========================================
        # Step 6: 合并结果
        # ========================================
        log_info "Step 6/7: 合并所有成功的解决方案"

        json_merge_unique \
            "$OUTPUT_DIR/solved_primary.json" \
            "$OUTPUT_DIR/solved_fallback.json" \
            "$OUTPUT_DIR/final_solved.json"

        TOTAL_SOLVED=$(json_length "$OUTPUT_DIR/final_solved.json")
        log_success "合并完成，共 $TOTAL_SOLVED 个解决方案"
    else
        log_info "Step 4-6/7: 跳过（所有问题已在主要模型中解决）"
        cp "$OUTPUT_DIR/solved_primary.json" "$OUTPUT_DIR/final_solved.json"
        TOTAL_SOLVED=$SOLVED_PRIMARY
        UNSOLVED_FINAL=0
    fi

    # ========================================
    # Step 7: 生成 TraceBench
    # ========================================
    log_info "Step 7/7: 生成 TraceBench 数据集"

    # MIGRATED 2026-05-15: original line was
    #   python3 generate_tracebench.py -i ... -o ... -d single_multi --validate --seed 42
    # That top-level wrapper does not exist. The canonical CLI is
    # src/cli/generate_data.py, which now drives TraceBenchGenerator directly.
    python3 -m src.cli.generate_data \
        --mode single \
        --format tracebench \
        --input "$OUTPUT_DIR/final_solved.json" \
        --output-dir "$OUTPUT_DIR" \
        --difficulty mixed \
        --validate \
        --seed 42 \
        2>&1 | tee "$OUTPUT_DIR/step7_tracebench.log"

    # generate_data.py writes a JSON inside $OUTPUT_DIR; conventionally named
    # tracebench.json. Symlink-or-rename if downstream tools expect that path.
    if [ -f "$OUTPUT_DIR/tracebench.json" ]; then
        :  # already correct
    elif [ -f "$OUTPUT_DIR/generated_single/tracebench.json" ]; then
        cp "$OUTPUT_DIR/generated_single/tracebench.json" "$OUTPUT_DIR/tracebench.json"
    fi

    TRACEBENCH_COUNT=$(json_length "$OUTPUT_DIR/tracebench.json")
    log_success "TraceBench 生成完成: $TRACEBENCH_COUNT 个样本"

    # ========================================
    # 生成统计报告
    # ========================================
    log_info "生成统计报告..."

    OVERALL_RATE=$(python3 -c "print(f'{$TOTAL_SOLVED * 100 / $FILTERED_COUNT:.1f}')")

    cat > "$OUTPUT_DIR/pipeline_report.json" <<EOF
{
  "pipeline_version": "1.0",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "input": {
    "file": "$INPUT",
    "min_depth": $MIN_DEPTH
  },
  "statistics": {
    "total_problems": $FILTERED_COUNT,
    "solved_primary": $SOLVED_PRIMARY,
    "solved_fallback": ${SOLVED_FALLBACK:-0},
    "total_solved": $TOTAL_SOLVED,
    "unsolved": $UNSOLVED_FINAL,
    "tracebench_samples": $TRACEBENCH_COUNT,
    "success_rate": "$OVERALL_RATE%"
  },
  "providers": {
    "primary": {
      "provider": "together",
      "model": "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
      "success": $SOLVED_PRIMARY,
      "rate": "$PRIMARY_RATE%"
    },
    "fallback": {
      "provider": "openai",
      "model": "gpt-4.1-mini",
      "success": ${SOLVED_FALLBACK:-0},
      "attempted": $UNSOLVED_PRIMARY
    }
  },
  "output_files": {
    "tracebench": "$OUTPUT_DIR/tracebench.json",
    "solved": "$OUTPUT_DIR/final_solved.json",
    "unsolved": "$OUTPUT_DIR/unsolved_final.json"
  }
}
EOF

    # ========================================
    # 创建 latest 软链接
    # ========================================
    if [ -d "output/latest" ] || [ -L "output/latest" ]; then
        rm -f output/latest
    fi
    ln -s "$(basename $OUTPUT_DIR)" output/latest

    # ========================================
    # 打印最终报告
    # ========================================
    echo ""
    log_info "================================================"
    log_success "Pipeline 运行完成!"
    log_info "================================================"
    echo ""
    echo "📊 统计摘要:"
    echo "  ├─ 过滤问题数: $FILTERED_COUNT"
    echo "  ├─ 主要模型成功: $SOLVED_PRIMARY ($PRIMARY_RATE%)"
    if [ "$UNSOLVED_PRIMARY" -gt 0 ]; then
        echo "  ├─ 备用模型成功: ${SOLVED_FALLBACK:-0}/$UNSOLVED_PRIMARY"
    fi
    echo "  ├─ 总体成功: $TOTAL_SOLVED/$FILTERED_COUNT ($OVERALL_RATE%)"
    echo "  ├─ 未解决: $UNSOLVED_FINAL"
    echo "  └─ TraceBench 样本: $TRACEBENCH_COUNT"
    echo ""
    echo "📁 输出文件:"
    echo "  ├─ TraceBench: $OUTPUT_DIR/tracebench.json"
    echo "  ├─ 已解决: $OUTPUT_DIR/final_solved.json"
    echo "  ├─ 未解决: $OUTPUT_DIR/unsolved_final.json"
    echo "  ├─ 报告: $OUTPUT_DIR/pipeline_report.json"
    echo "  └─ 最新运行: output/latest -> $(basename $OUTPUT_DIR)"
    echo ""

    # 检查成功率
    if [ "$TOTAL_SOLVED" -lt "$((FILTERED_COUNT * 80 / 100))" ]; then
        log_warning "成功率低于 80%，建议检查日志文件"
    fi

    if [ "$TRACEBENCH_COUNT" -lt "$((TOTAL_SOLVED * 90 / 100))" ]; then
        log_warning "TraceBench 注入成功率低于 90%，建议检查验证日志"
    fi
}

# 错误处理
trap 'log_error "Pipeline 执行失败，请查看日志文件"; exit 1' ERR

# 执行主流程
main

exit 0
