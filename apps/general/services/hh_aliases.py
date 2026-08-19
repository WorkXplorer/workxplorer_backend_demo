import re

from apps.skills.localization import clean_text, normalize_text, normalized_key, unique_items

_TOKEN_RE = re.compile(
    r"[0-9a-z\u0430-\u044f\u0451\u0493\u049b\u04b3\u045e\u04af\u0456\u0457]+"
)


MARKET_SEARCH_TOKEN_ALIASES = {
    "education": "Образование",
    "manufacturing": "Производство",
    "marketolog": "Маркетолог",
    "marketologist": "Маркетолог",
    "smm": "SMM",
    "doctor": "Врач",
    "physician": "Врач",
    "nurse": "Медсестра",
    "pharmacist": "Фармацевт",
    "dentist": "Стоматолог",
    "surgeon": "Хирург",
    "therapist": "Терапевт",
    "pediatrician": "Педиатр",
    "medicine": "Медицина",
    "medical": "Медицинский",
    "healthcare": "Здравоохранение",
    "shifokor": "Врач",
    "hamshira": "Медсестра",
    "accountant": "Бухгалтер",
    "economist": "Экономист",
    "financier": "Финансист",
    "auditor": "Аудитор",
    "finance": "Финансы",
    "accounting": "Бухгалтерия",
    "buxgalter": "Бухгалтер",
    "lawyer": "Юрист",
    "advocate": "Адвокат",
    "notary": "Нотариус",
    "seller": "Продавец",
    "salesperson": "Продавец",
    "salesman": "Продавец",
    "cashier": "Кассир",
    "sales": "Продажи",
    "merchandiser": "Мерчандайзер",
    "sotuvchi": "Продавец",
    "architect": "Архитектор",
    "builder": "Строитель",
    "constructor": "Конструктор",
    "construction": "Строительство",
    "arxitektor": "Архитектор",
    "chef": "Повар",
    "cook": "Повар",
    "waiter": "Официант",
    "bartender": "Бармен",
    "barista": "Бариста",
    "oshpaz": "Повар",
    "tutor": "Репетитор",
    "instructor": "Инструктор",
    "driver": "Водитель",
    "logistics": "Логистика",
    "courier": "Курьер",
    "dispatcher": "Диспетчер",
    "storekeeper": "Кладовщик",
    "warehouse": "Склад",
    "loader": "Грузчик",
    "haydovchi": "Водитель",
    "security": "Охранник",
    "guard": "Охранник",
    "recruiter": "Рекрутер",
    "director": "Директор",
    "hotel": "Гостиница",
    "tourism": "Туризм",
    "hospitality": "Гостиничный",
    "designer": "Дизайнер",
    "developer": "Разработчик",
    "programmer": "Программист",
    "engineer": "Инженер",
    "analyst": "Аналитик",
    "manager": "Менеджер",
    "coordinator": "Координатор",
    "specialist": "Специалист",
    "consultant": "Консультант",
    "administrator": "Администратор",
    "supervisor": "Супервайзер",
    "operator": "Оператор",
    "technician": "Техник",
    "researcher": "Исследователь",
    "scientist": "Исследователь",
    "trainer": "Тренер",
    "coach": "Тренер",
    "editor": "Редактор",
    "journalist": "Журналист",
    "copywriter": "Копирайтер",
    "writer": "Автор",
    "translator": "Переводчик",
    "interpreter": "Переводчик",
    "photographer": "Фотограф",
    "videographer": "Видеограф",
    "psychologist": "Психолог",
    "veterinarian": "Ветеринар",
    "electrician": "Электрик",
    "welder": "Сварщик",
    "plumber": "Сантехник",
    "agronomist": "Агроном",
    "financial": "Финансовый",
    "technical": "Технический",
    "project": "Проект",
    "product": "Продукт",
    "data": "Данные",
}


MARKET_SEARCH_VARIANT_ALIASES = {
    "education": ["Преподаватель", "Учитель", "Образование"],
    "manufacturing": [
        "Оператор производства",
        "Производственный рабочий",
        "Технолог производства",
        "Производство",
    ],
    "doctor": ["Врач", "Доктор", "Врач-терапевт", "Медицинский работник"],
    "physician": ["Врач", "Врач общей практики", "Терапевт"],
    "nurse": ["Медсестра", "Медицинская сестра", "Медработник"],
    "medicine": ["Врач", "Медицина", "Медицинский работник", "Здравоохранение"],
    "healthcare": ["Врач", "Медсестра", "Медицина", "Здравоохранение"],
    "shifokor": ["Врач", "Доктор", "Медицинский работник"],
    "accountant": ["Бухгалтер", "Главный бухгалтер", "Бухгалтерия"],
    "buxgalter": ["Бухгалтер", "Главный бухгалтер"],
    "economist": ["Экономист", "Финансист", "Финансовый аналитик"],
    "lawyer": ["Юрист", "Адвокат", "Юрисконсульт"],
    "chef": ["Повар", "Шеф-повар", "Технолог питания"],
    "cook": ["Повар", "Шеф-повар"],
    "oshpaz": ["Повар", "Шеф-повар"],
    "driver": ["Водитель", "Водитель-экспедитор", "Шофер"],
    "haydovchi": ["Водитель", "Водитель-экспедитор"],
    "architect": ["Архитектор", "Архитектор-проектировщик"],
    "seller": ["Продавец", "Продавец-консультант", "Торговый представитель"],
    "salesperson": ["Продавец", "Торговый представитель"],
    "sotuvchi": ["Продавец", "Продавец-консультант"],
}


PREFER_ALIASED_SEARCH_KEYS = {
    "manufacturing",
    "doctor",
    "physician",
    "nurse",
    "shifokor",
    "chef",
    "cook",
    "oshpaz",
    "driver",
    "haydovchi",
    "buxgalter",
}


MARKET_TOKEN_ALIASES = {
    "legal": "legal",
    "юрист": "legal",
    "юридический": "legal",
    "юридическая": "legal",
    "маркетолог": "marketolog",
    "маркетолога": "marketolog",
    "manufacturing": "manufacturing",
    "производство": "manufacturing",
    "производства": "manufacturing",
    "производственный": "manufacturing",
    "производственная": "manufacturing",
    "производстве": "manufacturing",
    "оператор": "operator",
    "рабочий": "worker",
    "технолог": "technologist",
    "education": "education",
    "teacher": "teacher",
    "преподаватель": "teacher",
    "преподавателя": "teacher",
    "учитель": "teacher",
    "учителя": "teacher",
    "смм": "smm",
    "developer": "developer",
    "разработчик": "developer",
    "разработчика": "developer",
    "разработчику": "developer",
    "программист": "developer",
    "программиста": "developer",
    "engineer": "engineer",
    "инженер": "engineer",
    "инженера": "engineer",
    "analyst": "analyst",
    "аналитик": "analyst",
    "аналитика": "analyst",
    "designer": "designer",
    "дизайнер": "designer",
    "дизайнера": "designer",
    "tester": "tester",
    "тестировщик": "tester",
    "тестировщика": "tester",
    "qa": "tester",
    "devops": "devops",
    "backend": "backend",
    "бэкенд": "backend",
    "бекенд": "backend",
    "frontend": "frontend",
    "фронтенд": "frontend",
    "фронт": "frontend",
    "fullstack": "fullstack",
    "full-stack": "fullstack",
    "фулстек": "fullstack",
    "doctor": "doctor",
    "врач": "doctor",
    "доктор": "doctor",
    "physician": "doctor",
    "shifokor": "doctor",
    "медицина": "medicine",
    "медицинский": "medical",
    "медицинская": "medical",
    "nurse": "nurse",
    "медсестра": "nurse",
    "медсестры": "nurse",
    "hamshira": "nurse",
    "pharmacist": "pharmacist",
    "фармацевт": "pharmacist",
    "dentist": "dentist",
    "стоматолог": "dentist",
    "surgeon": "surgeon",
    "хирург": "surgeon",
    "therapist": "therapist",
    "терапевт": "therapist",
    "педиатр": "pediatrician",
    "pediatrician": "pediatrician",
    "accountant": "accountant",
    "бухгалтер": "accountant",
    "бухгалтера": "accountant",
    "buxgalter": "accountant",
    "economist": "economist",
    "экономист": "economist",
    "financier": "financier",
    "финансист": "financier",
    "auditor": "auditor",
    "аудитор": "auditor",
    "seller": "seller",
    "salesperson": "seller",
    "salesman": "seller",
    "sotuvchi": "seller",
    "продавец": "seller",
    "продавца": "seller",
    "cashier": "cashier",
    "кассир": "cashier",
    "merchandiser": "merchandiser",
    "мерчандайзер": "merchandiser",
    "chef": "chef",
    "cook": "chef",
    "oshpaz": "chef",
    "повар": "chef",
    "повара": "chef",
    "шеф": "chef",
    "waiter": "waiter",
    "официант": "waiter",
    "bartender": "bartender",
    "бармен": "bartender",
    "barista": "barista",
    "бариста": "barista",
    "driver": "driver",
    "haydovchi": "driver",
    "водитель": "driver",
    "водителя": "driver",
    "шофер": "driver",
    "шофёр": "driver",
    "courier": "courier",
    "курьер": "courier",
    "dispatcher": "dispatcher",
    "диспетчер": "dispatcher",
    "storekeeper": "storekeeper",
    "кладовщик": "storekeeper",
    "loader": "loader",
    "грузчик": "loader",
    "security": "security",
    "guard": "security",
    "охранник": "security",
    "охранника": "security",
    "охрана": "security",
    "architect": "architect",
    "arxitektor": "architect",
    "архитектор": "architect",
    "архитектора": "architect",
    "builder": "builder",
    "строитель": "builder",
    "строителя": "builder",
    "constructor": "constructor",
    "конструктор": "constructor",
    "конструктора": "constructor",
    "recruiter": "recruiter",
    "рекрутер": "recruiter",
    "рекрутера": "recruiter",
    "director": "director",
    "директор": "director",
    "директора": "director",
    "hotel": "hotel",
    "гостиница": "hotel",
    "гостиничный": "hotel",
    "tourism": "tourism",
    "туризм": "tourism",
}

VACANCY_TITLE_STOPWORDS = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "of",
    "for",
    "to",
    "in",
    "with",
    "senior",
    "middle",
    "junior",
    "lead",
    "head",
    "chief",
    "intern",
    "manager",
    "specialist",
    "менеджер",
    "специалист",
    "стажер",
    "стажёр",
    "старший",
    "младший",
    "ведущий",
    "главный",
}


def apply_market_search_aliases(text):
    def replace_token(match):
        token = match.group(0)
        return MARKET_SEARCH_TOKEN_ALIASES.get(token.lower(), token)

    return clean_text(
        re.sub(
            r"[0-9a-zа-яёғқҳўүіїєçşöüğ#+.]+",
            replace_token,
            clean_text(text),
            flags=re.IGNORECASE,
        )
    )


def market_search_alias_variants(text):
    key = normalized_key(text)
    aliases = MARKET_SEARCH_VARIANT_ALIASES.get(key, [])
    return unique_items([*aliases, apply_market_search_aliases(text)])


def candidate_hh_search_query_variants(
    resume,
    market_query,
    title_query="",
    include_domain_fallback=True,
):
    domain_name = clean_text(resume.domain.name if resume.domain else "")
    title_query = clean_text(title_query)
    aliased_title_query = apply_market_search_aliases(title_query)
    aliased_market_query = apply_market_search_aliases(market_query)
    domain_aliases = market_search_alias_variants(domain_name)

    preferred_aliases = market_search_alias_variants(market_query)
    prefer_aliases = (
        normalized_key(market_query) in PREFER_ALIASED_SEARCH_KEYS
        and preferred_aliases
    )
    if prefer_aliases:
        candidates = preferred_aliases
    else:
        candidates = [market_query, aliased_market_query]
        individual_translations = unique_items([
            MARKET_SEARCH_TOKEN_ALIASES[tok]
            for tok in _TOKEN_RE.findall(market_query.lower())
            if tok in MARKET_SEARCH_TOKEN_ALIASES
        ])
        for translation in individual_translations:
            aliased_lower = normalized_key(aliased_market_query)
            if normalized_key(translation) not in aliased_lower:
                candidates.append(translation)
        if include_domain_fallback and domain_name:
            candidates.extend(domain_aliases)
            candidates.append(domain_name)
        if (
            domain_name
            and aliased_title_query
            and normalized_key(domain_name) not in normalized_key(aliased_title_query)
        ):
            candidates.append(f"{domain_name} {aliased_title_query}")
        candidates.extend([aliased_title_query, title_query])
    return unique_items(candidates)


def tokenize_market_text(text):
    return [
        MARKET_TOKEN_ALIASES.get(token, token)
        for token in re.findall(
            r"[0-9a-zа-яёғқҳўүіїєçşöüğ#+.]+",
            normalize_text(text),
        )
        if len(token) >= 2
    ]


def vacancy_title_matches_query(vacancy, query):
    query = clean_text(query)
    vacancy_title = clean_text(vacancy.get("title"))
    if not query or not vacancy_title:
        return True

    title_key = normalized_key(vacancy_title)
    query_key = normalized_key(query)
    if query_key and query_key in title_key:
        return True

    query_tokens = set(tokenize_market_text(query))
    title_tokens = set(tokenize_market_text(vacancy_title))
    if not query_tokens or not title_tokens:
        return True

    if "smm" in query_tokens and {"social", "media"} <= title_tokens:
        return True
    if "smm" in title_tokens and {"social", "media"} <= query_tokens:
        return True

    important_tokens = query_tokens - VACANCY_TITLE_STOPWORDS
    shared_important = important_tokens & title_tokens

    if important_tokens:
        required = 2 if len(important_tokens) >= 3 else 1
        if len(shared_important) >= required:
            return True
        return False

    return bool(query_tokens & title_tokens)


def filter_relevant_hh_vacancies(vacancies, query):
    return [
        vacancy
        for vacancy in vacancies
        if vacancy_title_matches_query(vacancy, query)
    ]
