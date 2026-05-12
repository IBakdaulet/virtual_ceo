"""Parsers for different news sources"""

from .bolashak_parser import BolashakParser
from .opportunitiescircle_parser import OpportunitiesCircleParser
from .opportunitiescorners_parser import OpportunitiesCornersParser
from .studyqa_parser import StudyQAParser
from .educationabroad_parser import EducationAbroadParser
from .topuniversities_parser import TopUniversitiesParser
from .brightscholarship_parser import BrightScholarshipParser
from .globalscholarships_parser import GlobalScholarshipsParser
from .spubl_parser import SpublParser
from .generic_parser import GenericParser

__all__ = [
    'BolashakParser',
    'OpportunitiesCircleParser',
    'OpportunitiesCornersParser',
    'StudyQAParser',
    'EducationAbroadParser',
    'TopUniversitiesParser',
    'BrightScholarshipParser',
    'GlobalScholarshipsParser',
    'SpublParser',
    'GenericParser',
]
