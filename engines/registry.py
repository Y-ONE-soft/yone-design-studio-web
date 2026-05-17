from engines.whitebook.engine import WhitebookEngine
from engines.blackbook.engine import BlackbookEngine
from engines.hanyoung.engine import HanyoungEngine
from engines.cover.engine import CoverEngine
from engines.cover_pocketbook.engine import CoverPocketbookEngine
from engines.pocketbook.engine import PocketbookEngine
from engines.final.engine import FinalEngine
from engines.workbook.engine import WorkbookEngine
from engines.baenje.engine import BaenjeEngine
from engines.textbook_workbook.engine import TextbookWorkbookEngine
from engines.ebs_workbook.engine import EbsWorkbookEngine
from engines.suneungteukgang_workbook.engine import SuneungteukgangWorkbookEngine
from engines.seseospecial.engine import SeseoSpecialEngine
from engines.mockexam.engine import MockexamEngine
from engines.mockexam_sero_merge.engine import MockexamSeroMergeEngine
from engines.analysis_merge.engine import AnalysisMergeEngine
from engines.mothertongue_merge.engine import MothertongueMergeEngine

# ── 새 교재 추가 시 여기에 한 줄만 추가 ──────────────────────────────────
_ENGINE_LIST = [
    WhitebookEngine(),
    BlackbookEngine(),
    BaenjeEngine(),
    HanyoungEngine(),
    CoverEngine(),
    CoverPocketbookEngine(),
    PocketbookEngine(),
    FinalEngine(),
    WorkbookEngine(),
    TextbookWorkbookEngine(),
    EbsWorkbookEngine(),
    SuneungteukgangWorkbookEngine(),
    SeseoSpecialEngine(),
    MockexamEngine(),
    MockexamSeroMergeEngine(),
    AnalysisMergeEngine(),
    MothertongueMergeEngine(),
]
# ────────────────────────────────────────────────────────────────────────

_REGISTRY: dict = {e.material_id: e for e in _ENGINE_LIST}


def get(material_id: str):
    engine = _REGISTRY.get(material_id)
    if not engine:
        raise KeyError(f"등록되지 않은 교재: {material_id}")
    return engine


def all_engines() -> list:
    return list(_REGISTRY.values())
