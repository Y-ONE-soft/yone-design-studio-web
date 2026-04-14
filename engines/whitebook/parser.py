import subprocess
import sys


def run_parse(parse_script: str, hwpx_files: list, answer_files: list,
              output_json: str, log) -> None:
    """
    parse_whitebook.py CLI를 subprocess로 호출.
    기존 파서 코드는 일절 수정하지 않고 그대로 재활용.

    CLI 인터페이스:
        python3 parse_whitebook.py <output.json> <hwpx1> [hwpx2 ...] [--answers <ans1> ...]
    """
    cmd = [sys.executable, parse_script, output_json] + hwpx_files
    if answer_files:
        cmd += ["--answers"] + answer_files

    log(f"[파서] 실행: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in proc.stdout:
        log(f"[파서] {line.rstrip()}")
    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"parse_whitebook.py 실패 (exit {proc.returncode})")
