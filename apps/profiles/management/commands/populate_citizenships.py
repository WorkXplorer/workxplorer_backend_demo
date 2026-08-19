from django.core.management.base import BaseCommand

from apps.profiles.models import Citizenship


class Command(BaseCommand):
    help = "Populate citizenship data with translations in three languages (en, ru, uz)"

    # Citizenship data: (name_en, name_ru, name_uz)
    CITIZENSHIPS = [
        ("Afghanistan", "Афганистан", "Afg'oniston"),
        ("Albania", "Албания", "Albaniya"),
        ("Algeria", "Алжир", "Jazoir"),
        ("Argentina", "Аргентина", "Argentina"),
        ("Armenia", "Армения", "Armaniston"),
        ("Australia", "Австралия", "Avstraliya"),
        ("Austria", "Австрия", "Avstriya"),
        ("Azerbaijan", "Азербайджан", "Ozarbayjon"),
        ("Bangladesh", "Бангладеш", "Bangladesh"),
        ("Belarus", "Беларусь", "Belarus"),
        ("Belgium", "Бельгия", "Belgiya"),
        ("Brazil", "Бразилия", "Braziliya"),
        ("Bulgaria", "Болгария", "Bolgariya"),
        ("Canada", "Канада", "Kanada"),
        ("Chile", "Чили", "Chili"),
        ("China", "Китай", "Xitoy"),
        ("Colombia", "Колумбия", "Kolumbiya"),
        ("Croatia", "Хорватия", "Xorvatiya"),
        ("Cuba", "Куба", "Kuba"),
        ("Czech Republic", "Чехия", "Chexiya"),
        ("Denmark", "Дания", "Daniya"),
        ("Egypt", "Египет", "Misr"),
        ("Estonia", "Эстония", "Estoniya"),
        ("Finland", "Финляндия", "Finlandiya"),
        ("France", "Франция", "Fransiya"),
        ("Georgia", "Грузия", "Gruziya"),
        ("Germany", "Германия", "Germaniya"),
        ("Greece", "Греция", "Gretsiya"),
        ("Hungary", "Венгрия", "Vengriya"),
        ("India", "Индия", "Hindiston"),
        ("Indonesia", "Индонезия", "Indoneziya"),
        ("Iran", "Иран", "Eron"),
        ("Iraq", "Ирак", "Iroq"),
        ("Ireland", "Ирландия", "Irlandiya"),
        ("Israel", "Израиль", "Isroil"),
        ("Italy", "Италия", "Italiya"),
        ("Japan", "Япония", "Yaponiya"),
        ("Jordan", "Иордания", "Iordaniya"),
        ("Kazakhstan", "Казахстан", "Qozog'iston"),
        ("Kenya", "Кения", "Keniya"),
        ("Kuwait", "Кувейт", "Quvayt"),
        ("Kyrgyzstan", "Кыргызстан", "Qirg'iziston"),
        ("Latvia", "Латвия", "Latviya"),
        ("Lebanon", "Ливан", "Livan"),
        ("Lithuania", "Литва", "Litva"),
        ("Malaysia", "Малайзия", "Malayziya"),
        ("Mexico", "Мексика", "Meksika"),
        ("Moldova", "Молдова", "Moldova"),
        ("Mongolia", "Монголия", "Mo'g'uliston"),
        ("Morocco", "Марокко", "Marokash"),
        ("Netherlands", "Нидерланды", "Niderlandiya"),
        ("New Zealand", "Новая Зеландия", "Yangi Zelandiya"),
        ("Nigeria", "Нигерия", "Nigeriya"),
        ("North Korea", "Северная Корея", "Shimoliy Koreya"),
        ("Norway", "Норвегия", "Norvegiya"),
        ("Pakistan", "Пакистан", "Pokiston"),
        ("Palestine", "Палестина", "Falastin"),
        ("Peru", "Перу", "Peru"),
        ("Philippines", "Филиппины", "Filippin"),
        ("Poland", "Польша", "Polsha"),
        ("Portugal", "Португалия", "Portugaliya"),
        ("Qatar", "Катар", "Qatar"),
        ("Romania", "Румыния", "Ruminiya"),
        ("Russia", "Россия", "Rossiya"),
        ("Saudi Arabia", "Саудовская Аравия", "Saudiya Arabistoni"),
        ("Serbia", "Сербия", "Serbiya"),
        ("Singapore", "Сингапур", "Singapur"),
        ("Slovakia", "Словакия", "Slovakiya"),
        ("Slovenia", "Словения", "Sloveniya"),
        ("South Africa", "Южная Африка", "Janubiy Afrika"),
        ("South Korea", "Южная Корея", "Janubiy Koreya"),
        ("Spain", "Испания", "Ispaniya"),
        ("Sweden", "Швеция", "Shvetsiya"),
        ("Switzerland", "Швейцария", "Shveytsariya"),
        ("Syria", "Сирия", "Suriya"),
        ("Taiwan", "Тайвань", "Tayvan"),
        ("Tajikistan", "Таджикистан", "Tojikiston"),
        ("Thailand", "Таиланд", "Tailand"),
        ("Tunisia", "Тунис", "Tunis"),
        ("Turkey", "Турция", "Turkiya"),
        ("Turkmenistan", "Туркменистан", "Turkmaniston"),
        ("Ukraine", "Украина", "Ukraina"),
        ("United Arab Emirates", "ОАЭ", "Birlashgan Arab Amirliklari"),
        ("United Kingdom", "Великобритания", "Buyuk Britaniya"),
        ("United States", "США", "Amerika Qo'shma Shtatlari"),
        ("Uzbekistan", "Узбекистан", "O'zbekiston"),
        ("Venezuela", "Венесуэла", "Venesuela"),
        ("Vietnam", "Вьетнам", "Vyetnam"),
        ("Yemen", "Йемен", "Yaman"),
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all existing citizenship data before populating",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted_count, _ = Citizenship.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Deleted {deleted_count} existing citizenship records")
            )

        created_count = 0
        updated_count = 0

        for name_en, name_ru, name_uz in self.CITIZENSHIPS:
            citizenship, created = Citizenship.objects.update_or_create(
                name_en=name_en,
                defaults={
                    "name": name_en,
                    "name_ru": name_ru,
                    "name_uz": name_uz,
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully populated citizenships: "
                f"{created_count} created, {updated_count} updated"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(f"Total citizenships in database: {Citizenship.objects.count()}")
        )
