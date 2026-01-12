# options/test_options.py

# ... 기존 import / class TestOptions(BaseOptions) ... 내부에서
def initialize(self, parser):
    parser = BaseOptions.initialize(self, parser)

    # ✅ (추가) JSON 출력 옵션
    parser.add_argument('--output_json', type=str, default=None,
                        help='Save summary(metrics+config+run) as JSON to this path')
    parser.add_argument('--output_jsonl', type=str, default=None,
                        help='Save per-sample predictions as JSONL to this path (one record per line)')
    parser.add_argument('--save_predictions', action='store_true',
                        help='If set, include per-sample predictions in output_json (can be huge)')

    return parser
