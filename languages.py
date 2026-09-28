"""Language choices shared by speech recognition and subtitle editing."""
LANGUAGES = [('Detect language', 'auto'), ('English', 'en'), ('Japanese', 'ja'),
    ('Chinese', 'zh'), ('Korean', 'ko'), ('Spanish', 'es'), ('French', 'fr'),
    ('German', 'de'), ('Portuguese', 'pt'), ('Italian', 'it'), ('Arabic', 'ar'),
    ('Hindi', 'hi'), ('Russian', 'ru'), ('Ukrainian', 'uk'), ('Dutch', 'nl'),
    ('Polish', 'pl'), ('Turkish', 'tr'), ('Vietnamese', 'vi'), ('Thai', 'th'),
    ('Indonesian', 'id'), ('Malay', 'ms'), ('Swedish', 'sv'), ('Danish', 'da'),
    ('Norwegian', 'no'), ('Finnish', 'fi'), ('Greek', 'el'), ('Czech', 'cs'),
    ('Romanian', 'ro'), ('Hungarian', 'hu'), ('Hebrew', 'he'), ('Bengali', 'bn'),
    ('Tamil', 'ta'), ('Telugu', 'te'), ('Persian', 'fa'), ('Urdu', 'ur'),
    ('Tagalog', 'tl'), ('Catalan', 'ca'), ('Slovak', 'sk'), ('Croatian', 'hr'),
    ('Serbian', 'sr'), ('Bulgarian', 'bg'), ('Slovenian', 'sl')]
# Keep automatic detection first, with every named language in display order.
LANGUAGES.sort(key=lambda item: (item[1] != 'auto', item[0].casefold()))
MODELS = ('base', 'small', 'medium', 'large-v3', 'base.en', 'small.en', 'medium.en')


def validate_language_model(language, model, task='transcribe'):
    if language not in {code for _, code in LANGUAGES}:
        raise ValueError('Choose a supported spoken language.')
    if model not in MODELS:
        raise ValueError('Choose a supported speech model.')
    if model.endswith('.en') and (language != 'en' or task == 'translate'):
        raise ValueError('English-only models cannot detect other languages or translate. '
                         'Choose base, small, medium, or large-v3.')


def language_name(code):
    return next((label for label, value in LANGUAGES if value == code), code)
