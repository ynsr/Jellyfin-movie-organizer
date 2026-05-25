from src.scrapers.doostihaa import parse_metadata_text


def test_parse_metadata_text_basic_fields():
    text = """
نام انیمیشن: آستریکس در سرزمین گل ها – Asterix the Gaul | تاریخ انتشار: سال 1967

زبان فیلم: دوبله فارسی گلوری + انگلیسی | ژانر: ماجراجویی | مدت: 65 دقیقه

محصول فرانسه | فرمت ویدئویی: MKV | حجم فیلم: 698 مگابایت
"""
    meta = parse_metadata_text(text)
    assert meta.title_fa == "آستریکس در سرزمین گل ها"
    assert meta.title_en == "Asterix the Gaul"
    assert meta.year == "1967"
    assert meta.duration_minutes == 65
    assert "ماجراجویی" in meta.genres
    assert "فرانسه" in meta.countries


def test_parse_metadata_text_plot():
    text = """
خلاصه داستان:
تام و جری در حین نقل مکان از ماشین جا می مانند و سپس با دختری آشنا میشوند که باید اون رو از دست عمه قلابی شیطان صفتش نجات دهند…

نام: نرمال – Normal | ژانر: اکشن، جنایی
"""
    meta = parse_metadata_text(text)
    assert "تام و جری" in meta.plot


def test_parse_metadata_text_imdb_rate():
    text = """
نام کارتون: جوجه کوچولو – Chicken Little | سال تولید: 2005 | ژانر: ماجراجویی، کمدی

امتیاز فیلم: 5.8 از 10
"""
    meta = parse_metadata_text(text)
    assert meta.year == "2005"
    assert meta.imdb_rate == "5.8"
    assert "ماجراجویی" in meta.genres
    assert "کمدی" in meta.genres
