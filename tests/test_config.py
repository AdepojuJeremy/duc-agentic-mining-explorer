from pathlib import Path

from duc_agentic_mining.config import load_config


def test_relative_paths_resolve_from_config(tmp_path: Path):
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    path = cfg_dir / "x.yaml"
    path.write_text(
        '''
output_root: ../runs
target_passed: 1
corpus:
  index_path: ../data/i.sqlite
  input_paths: [../data/x.jsonl]
roles:
  explorer: {model: test}
  validator: {model: test}
  generator: {model: test}
  reviewer: {model: test}
'''
    )
    cfg = load_config(path)
    assert cfg.corpus.input_paths[0].is_absolute()
    assert cfg.corpus.index_path.is_absolute()
    assert cfg.output_root.is_absolute()
