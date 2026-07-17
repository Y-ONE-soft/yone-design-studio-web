from engines.whitebook.engine import WhitebookEngine
from engines.blackbook.engine import BlackbookEngine
from engines.hanyoung.engine import HanyoungEngine
from engines.cover.engine import CoverEngine
from engines.cover_pocketbook.engine import CoverPocketbookEngine
from engines.final_cover.engine import FinalCoverEngine
from engines.pocketbook.engine import PocketbookEngine
from engines.final.engine import FinalEngine
from engines.workbook.engine import WorkbookEngine
from engines.workbook_sero.engine import WorkbookSeroEngine
from engines.workbook_supp.engine import WorkbookSuppEngine
from engines.baenje.engine import BaenjeEngine
from engines.textbook_workbook.engine import TextbookWorkbookEngine
from engines.ebs_workbook.engine import EbsWorkbookEngine
from engines.suneungteukgang_workbook.engine import SuneungteukgangWorkbookEngine
from engines.seseospecial.engine import SeseoSpecialEngine
from engines.mockexam.engine import MockexamEngine
from engines.mockexam_v2.engine import MockexamV2Engine
from engines.blackbook_v2.engine import BlackbookV2Engine
from engines.workbook_v2.engine import WorkbookV2Engine
from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine
from engines.workbook_sero_v2.engine import WorkbookSeroV2Engine
from engines.mockexam_sero_merge.engine import MockexamSeroMergeEngine
from engines.analysis_merge.engine import AnalysisMergeEngine
from engines.mothertongue_merge.engine import MothertongueMergeEngine
from engines.vert_to_horiz.engine import VertToHorizEngine
from engines.whitebook_v2.engine import WhitebookV2Engine
from engines.seseospecial_v2.engine import SeseoSpecialV2Engine
from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
from engines.ebs_workbook_v2.engine import EbsWorkbookV2Engine
from engines.suneungteukgang_workbook_v2.engine import (
    SuneungteukgangWorkbookV2Engine)
from engines.slim_merge.engine import SlimMergeEngine
from engines.mockexam_horiz_merge.engine import MockexamHorizMergeEngine
from engines.passage_remove.engine import PassageRemoveEngine
from engines.convert_to_vertical.engine import ConvertToVerticalEngine

# ── 새 교재 추가 시 여기에 한 줄만 추가 ──────────────────────────────────
_ENGINE_LIST = [
    WhitebookEngine(),
    BlackbookEngine(),
    BaenjeEngine(),
    HanyoungEngine(),
    CoverEngine(),
    CoverPocketbookEngine(),
    FinalCoverEngine(),
    PocketbookEngine(),
    FinalEngine(),
    WorkbookEngine(),
    WorkbookSeroEngine(),
    WorkbookSuppEngine(),
    TextbookWorkbookEngine(),
    EbsWorkbookEngine(),
    SuneungteukgangWorkbookEngine(),
    SeseoSpecialEngine(),
    MockexamEngine(),
    MockexamSeroMergeEngine(),
    AnalysisMergeEngine(),
    MothertongueMergeEngine(),
    VertToHorizEngine(),
    MockexamV2Engine(),
    BlackbookV2Engine(),
    WorkbookV2Engine(),
    WorkbookSuppV2Engine(),
    WorkbookSeroV2Engine(),
    WhitebookV2Engine(),
    SeseoSpecialV2Engine(),
    TextbookWorkbookV2Engine(),
    EbsWorkbookV2Engine(),
    SuneungteukgangWorkbookV2Engine(),
    SlimMergeEngine(),
    MockexamHorizMergeEngine(),
    PassageRemoveEngine(),
    ConvertToVerticalEngine(),
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
