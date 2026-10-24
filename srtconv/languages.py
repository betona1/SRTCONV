"""지원 언어 표. 각 엔진별 코드 매핑을 한곳에서 관리합니다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str        # 내부 코드 (Whisper 코드 기준)
    name_ko: str     # UI 표시 이름
    nllb: str        # NLLB-200 코드
    google: str      # Google 번역 코드
    mymemory: str    # MyMemory 코드
    whisper: str     # Whisper 언어 코드 (zh-TW 등은 zh 로 묶임)

    @property
    def m2m(self):
        """M2M100 언어 코드 (Whisper 코드와 같음, 번체 중국어는 zh 로 묶임)."""
        return self.whisper


LANGUAGES = [
    Language('ko', '한국어', 'kor_Hang', 'ko', 'ko-KR', 'ko'),
    Language('en', '영어', 'eng_Latn', 'en', 'en-US', 'en'),
    Language('ja', '일본어', 'jpn_Jpan', 'ja', 'ja-JP', 'ja'),
    Language('zh', '중국어(간체)', 'zho_Hans', 'zh-CN', 'zh-CN', 'zh'),
    Language('zh-TW', '중국어(번체)', 'zho_Hant', 'zh-TW', 'zh-TW', 'zh'),
    Language('es', '스페인어', 'spa_Latn', 'es', 'es-ES', 'es'),
    Language('fr', '프랑스어', 'fra_Latn', 'fr', 'fr-FR', 'fr'),
    Language('de', '독일어', 'deu_Latn', 'de', 'de-DE', 'de'),
    Language('pt', '포르투갈어', 'por_Latn', 'pt', 'pt-PT', 'pt'),
    Language('it', '이탈리아어', 'ita_Latn', 'it', 'it-IT', 'it'),
    Language('ru', '러시아어', 'rus_Cyrl', 'ru', 'ru-RU', 'ru'),
    Language('vi', '베트남어', 'vie_Latn', 'vi', 'vi-VN', 'vi'),
    Language('th', '태국어', 'tha_Thai', 'th', 'th-TH', 'th'),
    Language('id', '인도네시아어', 'ind_Latn', 'id', 'id-ID', 'id'),
    Language('ar', '아랍어', 'arb_Arab', 'ar', 'ar-SA', 'ar'),
    Language('hi', '힌디어', 'hin_Deva', 'hi', 'hi-IN', 'hi'),
    Language('tr', '터키어', 'tur_Latn', 'tr', 'tr-TR', 'tr'),
]

BY_CODE = {lang.code: lang for lang in LANGUAGES}
AUTO = 'auto'


def get(code):
    """내부 코드 또는 Whisper 감지 코드로 Language 를 찾습니다. 없으면 None."""
    if code in BY_CODE:
        return BY_CODE[code]
    for lang in LANGUAGES:
        if lang.whisper == code:
            return lang
    return None


def display_name(code):
    if code == AUTO:
        return '자동 감지'
    lang = get(code)
    return lang.name_ko if lang else code
