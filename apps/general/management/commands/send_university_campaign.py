import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.general.services.campaign_email_service import ManualEmailCampaignService

logger = logging.getLogger(__name__)

# Educational partners to target, exported from the Django admin and
# language-classified by institution affiliation (Russian federal branches
# -> ru, Western/English-medium branches -> en, everything else -> uz).
# (edupartner_id, name, language, recipient_limit-or-None)
UNIVERSITIES: list[tuple[str, str, str, int | None]] = [
    ("019d0172-8fe8-71de-a157-fa18a0b669c6", "A branch of the Federal State Budget Higher Education Institution \"Russian State Pedagogical University named after A.I. Gersen\" in Tashkent (Herzen-TB)", "ru", None),
    ("019d0172-8ef3-7eab-bccc-68ddf0d916e4", "Abu Rayhan Beruniy University (ARBU)", "uz", None),
    ("019d0172-8f52-7238-8aa7-a0143c939f1d", "Academy of Labor and Social Relations (ALSR)", "uz", None),
    ("019d0172-8f86-7aa5-96a4-1785f0473022", "Academy of Law Enforcement of the Republic of Uzbekistan (ALE)", "uz", None),
    ("019d0172-8ef6-77c5-a532-d3313b211730", "Acharya University (Acharya)", "en", None),
    ("019d0172-8ef7-752b-b0b0-c03f922a55a0", "Alfraganus University (AFU)", "uz", None),
    ("019d0172-8ef9-775a-ad09-722a77c15faa", "Al-Khwarizmi University (AKU)", "uz", None),
    ("019d0172-8f6d-7a9c-9d10-850f1c7e3cfe", "Almalyk State Technical Institute (AlmSTI)", "uz", None),
    ("019d0172-8efa-795a-83a0-f33c72aacba3", "American University of Technology (AUT)", "en", None),
    ("019d0172-8fea-772f-8b3a-f451480a771d", "Amiti University in Tashkent (Amity-TB)", "en", None),
    ("019e16ea-32aa-74fa-bcd8-41c716d74422", "Amity University (Amity)", "en", None),
    ("019d0172-8f04-789a-afe3-8ac807479c03", "Andijan Institute of Agriculture and Agrotechnologies (AIAA)", "uz", None),
    ("019d0172-8efd-7f95-bbe8-932dce57ae69", "Andijan State Institute of foreign languages (ASIFL)", "uz", None),
    ("019d0172-8f01-73fc-8ad0-fe59cd299bfe", "Andijan State Medical Institute (ASMI)", "uz", None),
    ("019d0172-8efe-71c2-ac1b-0c2c4a4daa7e", "Andijan State Pedagogical Institute (ASPI)", "uz", None),
    ("019d0172-8f03-7ae8-9a98-11d164e87466", "Andijan State University (ASU)", "uz", None),
    ("019d0172-8f00-7ce3-8709-ef7de186d1d5", "Andijon State Technical Institute (AndSTI)", "uz", None),
    ("019d0172-8f05-7d20-bbaf-d23570035281", "Angren University (AU)", "uz", None),
    ("019d0172-8f71-7cc5-8a48-3dd1ae67215c", "Asia international university (AIU)", "uz", None),
    ("019d0172-8f70-77e3-96c3-25672f57789b", "Asian University of Technology (AUT)", "uz", None),
    ("019d0172-8feb-7bb9-95bc-121365253d4a", "Belarusian-Uzbekistan Institute of Intersectoral Practical Technical Qualifications in Tashkent (BUIIPTQ)", "uz", None),
    ("019d0172-8f08-7d99-a78b-cbe8a1a7fbe5", "Branch of Astrakhan State Technical University in Tashkent region (ASTU-TB)", "ru", None),
    ("019d0172-8f4a-79cc-a134-d0f788533e7c", "Branch of Kazan Federal University in Jizzakh (KFU-JB)", "ru", None),
    ("019d0172-8fee-740d-bb1b-253a35c5e956", "Branch of N.E. Bauman Moscow State Technical University in Tashkent (BMSTU-TB)", "ru", None),
    ("019d0172-8f99-71dc-95e2-64fbe6229aaf", "Branch of the Federal state autonomous higher education institution\" Moscow State Institute of International Relations (University) of the Ministry of Foreign Affairs of the Russian Federation \" in Ta (MGIMO-TB)", "ru", None),
    ("019d0172-8f4e-745b-8c52-f1a832d922d6", "Branch of the Higher School of information systems management of Latvia in Fergana (ISMA-F)", "uz", None),
    ("019d0172-8f5a-740d-846f-8f09eab241b2", "Branch of the South Kazakhstan University named after M Auezov in Chirchik (Auezov-ChB)", "uz", None),
    ("019d0172-8f0e-7274-87df-734dd971a011", "British Management University (BMU)", "en", None),
    ("019d0172-8f16-724e-b584-fc4a2ed4c2e7", "Bukhara Institute of innovative medicine (BIIM)", "uz", None),
    ("019d0172-8f19-79be-b8ab-25fe7295a254", "Bukhara Institute of psychology and foreign languages (BIPFL)", "uz", None),
    ("019d0172-8f12-7670-8568-d4999c03980b", "Bukhara State Medical Institute (BSMI)", "uz", None),
    ("019d0172-8f10-7a8d-a988-2887d7be1c34", "Bukhara State Pedagogical Institute (BSPI)", "uz", None),
    ("019d0172-8f11-7718-95fc-a7206753b364", "Bukhara State Technical University (BSTU)", "uz", None),
    ("019d0172-8f14-7af7-8b24-94196e1734bf", "Bukhara State University (BSU)", "uz", None),
    ("019d0172-8f17-79c0-a0ca-59adaccfa87c", "Bukhara University of innovation (BUI)", "uz", None),
    ("019d0172-8ff6-7cd8-be41-ed86ce8c1fae", "Center for implementation of educational programs of Webster University in Tashkent (Webster)", "en", None),
    ("019d0172-8f1a-78da-bcee-efcbf7ee52e7", "Central Asian Medical University (CAMU)", "uz", None),
    ("019d0172-8f1c-71d6-9618-263c208fb1e7", "CENTRAL ASIAN UNIVERSITY (CAU)", "uz", None),
    ("019d0172-8f50-7d21-a245-16b4434e0b49", "Central Asian University of Environmental and Climate Change Studies (Green University) (GreenU (CAUECC))", "uz", None),
    ("019d0172-8fd4-7875-8263-68fd0dceec71", "Chirchik branch of Tashkent State Medical University (TMA-ChB)", "uz", None),
    ("019d0172-8f1d-7800-87c0-ee1bced9382d", "Chirchik State Pedagogical University (ChSPU)", "uz", None),
    ("019d0172-8f1e-7ce6-acd3-548dd6cb6f0f", "\"Collegium Humanum\" Warsaw University of Management Andijan Branch (CHWM-AF)", "en", None),
    ("019d0172-8f20-7b53-a4f0-29611c1cc3fb", "Cyber university (CSU)", "uz", None),
    ("019d0172-8f22-7d88-97ce-8b6c7dc406f2", "Denov Institute of Entrepreneurship and Pedagogy (DIEP)", "uz", None),
    ("019d0172-8f23-76c8-80b5-4219d4f8ec8a", "Digital university (DU)", "uz", None),
    ("019d0172-8f27-70f6-8431-36b58f8a9166", "Diplomat University (DiplomatU)", "uz", None),
    ("019d0172-8f28-7509-a8bc-923f2000b800", "EMU-UNIVERSITY (EMU)", "en", None),
    ("019d0172-8f33-7390-8be2-4ef8a16b1a13", "Federal state autonomous higher educational institution National Technological Research University MISiS branch in Olmalik city (MISiS-Alm)", "ru", None),
    ("019d0172-8f2d-7b6f-a8dc-fb2ffaebd554", "Fergana Public Health Medical Institute (FPHMI)", "uz", None),
    ("019d0172-8f2b-7a3b-9133-eb43ab2e57b1", "Fergana State Technical University (FerSTU)", "uz", None),
    ("019d0172-8f2c-7321-8307-47021d6dbd07", "Fergana State University (FerSU)", "uz", None),
    ("019d0172-8f3b-78eb-ac11-6cd955477dd6", "GUBKIN RUSSIAN STATE UNIVERSITY OF OIL AND GAS BRANCH IN TASHKENT (Gubkin-TB)", "ru", None),
    ("019d0172-8f36-7200-81d8-5310fd8e8d84", "Gulistan State Pedagogical Institute (GulSPI)", "uz", None),
    ("019d0172-8f37-74c2-a82f-a912b547c0f2", "Gulistan State University (GulSU)", "uz", None),
    ("019d0172-8f3d-756c-936c-6447b46d808a", "IMPULS BSR (IMPULS BSR)", "uz", None),
    ("019d0172-8fec-74e5-a2da-d9fb8693ff30", "Inha University, Tashkent (IUT)", "en", None),
    ("019d0172-8f3a-742e-9bc4-852ad7782fdf", "Institute of Social and Political Sciences (ISPS)", "uz", None),
    ("019d0172-9012-78e4-9f55-e0fec3231de7", "International Innovation University (IIU)", "uz", None),
    ("019d0172-8f82-73c3-9a79-9770cca28b1f", "International Institute of Food Technology and Engineering (IIFTE)", "uz", None),
    ("019d0172-9015-7ae2-86b9-93903e71bd3a", "International Nordic University (NordicU (INU))", "en", None),
    ("019d0172-8f3e-7bc1-a5f8-c5e7aa7774a9", "International School of Finance Technology and Science (ISFT)", "uz", None),
    ("019d0172-9018-7251-a955-7701e9aa5064", "International University of Agriculture (IAU)", "uz", None),
    ("019d0172-8f2f-70c0-ad30-fad477877906", "International University of Korea in Fergana (IUKF)", "uz", None),
    ("019d0172-9010-7223-8eae-aedad292376c", "International University of Social Innovation (IUSI)", "uz", None),
    ("019d0172-8ffd-79a7-843c-d2ff902f25b7", "International University of Turkic States (IUTS)", "uz", None),
    ("019d0172-8f43-744f-9b69-e767201d6feb", "IT Park University (ITPU)", "en", None),
    ("019d0172-8f46-74af-be12-92c45fc34e97", "Japan digital university (JDU)", "uz", None),
    ("019d0172-8f56-74fe-b6a7-ac03781f801e", "Jizzakh branch of the National University of Uzbekistan named after Mirzo Ulug'bek (NUU-JB)", "uz", None),
    ("019d0172-8f49-7c1b-a90c-988f7376441e", "Jizzakh Polytechnic Institute (JPI)", "uz", None),
    ("019d0172-8f47-7b5b-b481-36640e20d844", "Jizzakh State Pedagogical University (JSPU)", "uz", None),
    ("019d0172-8f4c-7044-8c3e-612a587f8fc4", "Kamoliddin Behzod National Institute of Painting and Design (KBNIPD)", "uz", None),
    ("019d0172-8f94-7e08-860a-695db459e08c", "Karakalpakstan Institute of Agriculture and Agrotechnologies (KIAAT)", "uz", None),
    ("019d0172-8f95-73ed-ae70-0eee0511864d", "Karakalpakstan Medical Institute (KMI)", "uz", None),
    ("019d0172-8f0b-7c6c-99e8-e3eb84b8ad95", "Karakalpak State University named after Berdak (KSU (Berdak))", "uz", None),
    ("019d0172-8f8f-70c4-b81e-bb3f87ee3a7f", "Karshi International University (KarIU)", "uz", None),
    ("019d0172-8f8d-7c2c-b504-35d5c0933e35", "Karshi State Technical University (KarSTU)", "uz", None),
    ("019d0172-8f8e-7ee1-a315-5eaa1961b7d5", "Karshi State University (KarSU)", "uz", None),
    ("019d0172-8f4d-7003-8522-c68a1b7311f1", "Kattakurgan State Pedagogical Institute (KaSPI)", "uz", None),
    ("019eb07c-f7eb-7166-b235-b5b2d9a3cd30", "Kazan State Power Engineering University (KSPEU)", "ru", None),
    ("019d0172-8f91-75f4-97aa-0f492c2b5979", "Kokand State University (KokSU)", "uz", None),
    ("019d0172-8f92-788f-a29a-43a960290137", "Kokan University (KokanU)", "uz", None),
    ("019d0172-8f59-7521-9633-1ec31d5ca124", "Lomonosov Moscow State University branch in Tashkent (MSU-TB)", "ru", None),
    ("019d0172-8f51-7320-9a05-3cce348a408b", "Mamun University (MamunU)", "uz", None),
    ("019d0172-8f58-7464-a5de-f1b4eccba8d9", "MMFI National Research Nuclear University branch of the federal state autonomous higher education institution in Tashkent (MEPhI-TB)", "ru", None),
    ("019d0172-8f5c-7f70-8e60-e1f401425687", "Namangan State Institute of foreign languages (NamSIFL)", "uz", None),
    ("019d0172-8f5d-7534-a806-3cc6b8d531d3", "Namangan State Pedagogical Institute (NamSPI)", "uz", None),
    ("019d0172-8f5f-77b9-876a-adcc6236d684", "Namangan State Technical University (NamSTU)", "uz", None),
    ("019d0172-8f60-7ea8-bfba-67c3085c24cf", "Namangan State University (NamSU)", "uz", None),
    ("019d0172-8f55-758b-8e8e-e605b499caac", "National hope university (NHU)", "uz", None),
    ("019d0172-901e-7ff7-a339-517ca772abaf", "National Institute of musical arts of Uzbekistan named after Yunus Rajabi (NIMAU)", "uz", None),
    ("019d0172-8f0c-70e5-b5ff-00d137d3cab1", "National Institute of Pop Art named after Botir Zakirov (BZNIPA)", "uz", None),
    ("019d0172-8f80-797d-98fb-427bcb880d17", "National University of Uzbekistan (NUUz)", "uz", None),
    ("019d0172-8f64-77a6-be32-840b626ac828", "Navoi institute of innovation (NavII)", "uz", None),
    ("019d0172-8f63-78bf-b211-9ca8d185c2c9", "Navoi State University (NavSU)", "uz", None),
    ("019d0172-8f61-7a2d-ba6e-74ee32be49f2", "Navoi State University of Mining and Technology (NSUMT)", "uz", None),
    ("019d0172-901a-7ebd-95d8-93990a7475a4", "New Century University (NCU)", "uz", None),
    ("019d0172-901c-7141-81c5-e6b87e81bc3d", "New Uzbekistan University (NewUU)", "en", None),
    ("019d0172-8f6b-72d9-9303-6e72f32332c2", "Nukus branch of the State Conservatory of Uzbekistan (SCU-NB)", "uz", None),
    ("019d0172-8f79-78b4-b9dc-b9ec162f1eff", "Nukus branch of the State Institute of Art and Culture of Uzbekistan (SIACU-NB)", "uz", None),
    ("019d0172-8f75-7f36-aa6e-0537a04e4fc9", "Nukus branch of Uzbekistan State University of Physical Education and Sports (UzSPESU-NB)", "uz", None),
    ("019d0172-8f69-733e-a3a8-9043b3c7e114", "Nukus Innovation Institute (NukII)", "uz", None),
    ("019d0172-8f67-7e85-9a7c-6c510732a85e", "Nukus State Pedagogical Institute (NukSPI)", "uz", None),
    ("019d0172-8f68-73e7-806a-06ed36d4e782", "Nukus State Technical University (NukSTU)", "uz", None),
    ("019d0172-8f6f-7d35-9144-3ff8029f4588", "Oriental University (OU)", "uz", None),
    ("019d0172-8f88-7f39-8d57-71f16bccb33f", "PDP University (PDP)", "uz", None),
    ("019d0172-8f89-7d52-a4af-1a2725936c57", "Perfect University (PerfectU)", "uz", None),
    ("019d0172-8f30-764f-aab3-d24145d11bfd", "Pharmaceutical Education and Research Institute (PERI)", "uz", None),
    ("019d0172-8f32-7b6d-a353-bdd977d2ee00", "Pharmaceutical Technical University (PTU)", "uz", None),
    ("019d0172-8f8a-7f71-9222-a84998093310", "Pisa university in Tashkent (Pisa-TB)", "en", None),
    ("019d0172-8f8b-7891-a744-f48312bb4e15", "Profi University (ProfiU)", "uz", None),
    ("019d0172-8fef-7e1e-8a9e-307ce1aa2288", "Puchon University (Puchon-TB)", "ru", None),
    ("019d0172-8f98-722c-92cc-8b28738c2e01", "Renaissance Educational University (REU)", "uz", None),
    ("019d0172-8ff0-7258-9097-a36bc1589b45", "\"S.A.\" in Tashkent All-Russian State Institute of Cinematography named after Gerasimov is a branch of the federal state budget higher education institution (VGIK-TB)", "ru", None),
    ("019d0172-8fcd-798c-8c23-8c2a009e7aa8", "Samarkand branch of Tashkent State University of Economics (TSUE-SamB)", "uz", None),
    ("019d0172-8fc9-7775-bafc-b270efca17b5", "Samarkand branch of Tashkent University of Information Technologies (TUIT-SamB)", "uz", None),
    ("019d0172-8f9a-7eb7-bfe7-4d7ae6102f04", "Samarkand Institute of agro-innovation and research (SamAIIR)", "uz", None),
    ("019d0172-8fa7-73ac-b718-a95255a8bb37", "Samarkand Institute of Economics and Service (SIES)", "uz", None),
    ("019d0172-8fa8-761b-98f5-a0f0c9fd6326", "Samarkand international university of technology (SIUT)", "uz", None),
    ("019d0172-8f9d-7beb-b1f5-94112985debd", "Samarkand State Institute of Foreign Languages (SamSIFL)", "uz", None),
    ("019d0172-8fa0-7d8c-81df-26f469faa2f4", "Samarkand State Medical University (SSMU)", "uz", None),
    ("019d0172-8f9e-7026-af93-f28add8ad2f1", "Samarkand State Pedagogical Institute (SamSPI)", "uz", None),
    ("019d0172-8faf-7a6b-869c-69e6aa5e7ded", "Samarkand State University named after Sharof Rashidov (SamSU)", "uz", None),
    ("019d0172-8f9c-7d7f-9bf8-f5750eeabdef", "Samarkand State University of Architecture and Construction (SamSACU)", "uz", None),
    ("019d0172-8fa1-7085-869c-91d9f4ca8df6", "Samarkand State University of Veterinary Medicine, Animal Husbandry and Biotechnology (SSUVMAHB)", "uz", None),
    ("019d0172-8fa3-7e2e-8449-3823f99e7e0b", "Samarkand State Veterinary Medicine, Animal Husbandry and Biotechnology University, Nukus branch (SSUVMAHB-NB)", "uz", None),
    ("019d0172-8faa-792b-9a56-06566be034d4", "SAMBHRAM University (Sambhram)", "en", None),
    ("019d0172-8fac-7db1-94f9-d95bc56e3503", "Sarbon University (SarbonU)", "uz", None),
    ("019d0172-8fae-7978-a4dd-82981fc97d79", "Shahrisabz State Pedagogical Institute (ShSPI)", "uz", None),
    ("019d0172-8f85-76a2-8912-082ae9caa369", "Sharda University in Uzbekistan (Sharda)", "en", None),
    ("019d0172-8fb2-7551-a15a-9686e214603b", "Sharq University (SharqU)", "uz", None),
    ("019d0172-8f3f-71d6-a43a-2bca640fe405", "Silk Road Innovation University (SRIU)", "uz", None),
    ("019d0172-8f41-7883-bfbd-a4a08de0eea0", "\"Silk Road\" International University of Tourism and Cultural Heritage (IUTCH)", "uz", None),
    ("019d0172-8ff2-7a86-af1e-53a0843aa1c9", "Singapore Institute for management development in Tashkent (MDIS-TB)", "en", None),
    ("019d0172-8fb3-75ce-b00f-55d66bed1001", "STARS International University (STARS)", "uz", None),
    ("019d0172-8f7c-7f4c-925c-c6380149a44b", "State Academy of Choreography of Uzbekistan (SACU)", "uz", None),
    ("019d0172-8f77-7351-b0b7-0799321a8a63", "State Conservatory of Uzbekistan (SCU)", "uz", None),
    ("019d0172-8f78-7d8d-9862-12fe8847610c", "State Institute of Art and Culture of Uzbekistan (SIACU)", "uz", None),
    ("019d0172-8fab-7700-ba8c-960cdb04087b", "\"St. Petersburg State University\" is a branch of the Federal State Budget Higher Education Institution in Tashkent (SPbU-TB)", "ru", None),
    ("019d0172-8f65-71c9-bffd-4f5bac6d33f3", "Tashkent branch of Russian National Research Medical University named after N.I. Pirogov (RNIMU-TB)", "ru", None),
    ("019d0172-8fa5-7fa0-8d0c-2b0624a94d8e", "Tashkent branch of Samarkand State Veterinary Medicine, Animal Husbandry and Biotechnology University (SSUVMAHB-TB)", "uz", None),
    ("019d0172-8f54-74d5-8cba-8c9113ae1513", "Tashkent branch of the federal state budgetary institution of higher education of the MEI National Research University (MPEI-TB)", "ru", None),
    ("019d0172-8f25-7aec-aa61-80fe8ede5a15", "Tashkent branch of the federal state budgetary institution of higher education of the Russian chemical and Technology University named after Mendeleev (MUCTR-TB)", "ru", None),
    ("019d0172-8f39-7f90-bc25-f398668e8186", "Tashkent branch of the Plekhanov Russian University of Economics (PRUE-TB)", "ru", None),
    ("019d0172-8fdb-79c3-bf12-bf67c889234a", "Tashkent Humanitarian University (THU)", "uz", None),
    ("019d0172-8fe2-7d5c-9079-773646cbc79c", "Tashkent Institute of Chemical Technology (TICT)", "uz", None),
    ("019d0172-8fdd-7234-b2ba-b528dc35e492", "Tashkent Institute of Economics and pedagogy (TIEP)", "uz", None),
    ("019d0172-8fe0-7b13-860b-c9a7caed5c48", "\"Tashkent Institute of Irrigation and Agricultural Mechanization Engineers\" National Research University (TIIAME)", "uz", None),
    ("019d0172-8fe6-7c55-862f-132afbba5f61", "Tashkent Institute of management and economics (TMII)", "uz", None),
    ("019d0172-8fe4-7f37-a9ba-3bff98e3c695", "Tashkent International University of Chemistry (TIUC)", "uz", None),
    ("019d0172-8fb6-7370-b456-07475e4a7e91", "Tashkent international university of education (TIUE)", "uz", None),
    ("019d0172-8ff9-7e24-a18c-8b1ec823d21d", "Tashkent International University of Financial Management and Technology (TIUFMT)", "uz", None),
    ("019d0172-8ffa-791c-840a-333896485b09", "Tashkent International University Of Westminster (WIUT)", "en", None),
    ("019d0172-8fb5-74ec-afa5-55ac9ee262c2", "Tashkent international university (TIU)", "uz", None),
    ("019d0172-8fb7-7f8b-9558-f28a33eacaf0", "Tashkent Metropolitan University (TMU)", "uz", None),
    ("019d0172-8fd9-786f-a155-07ef0bf84da0", "Tashkent Pharmaceutical Institute (TPI)", "uz", None),
    ("019d0172-8fcb-7c4a-aaf1-e1b4fe14e0c7", "Tashkent State Agrarian University (TSAU)", "uz", None),
    ("019d0172-8fd8-79a6-9a22-34e9b2936309", "Tashkent State Law University (TSUL)", "uz", None),
    ("019d0172-8fd1-782d-b6eb-1fae12309b43", "Tashkent State Technical University (TSTU)", "uz", None),
    ("019d0172-8fd7-79e2-94f2-0095ddb14694", "Tashkent State Transport University (TSTrU)", "uz", None),
    ("019d0172-8fcc-737c-8d46-ab752cbbaf78", "Tashkent State University of Economics (TSUE)", "uz", None),
    ("019d0172-8fd0-7ab5-81f2-9db94ddcca70", "Tashkent State University of Oriental Studies (TSUOS)", "uz", None),
    ("019d0172-8fcf-7e7d-afb0-ca1f0aaa0869", "Tashkent State University of Uzbek Language and Literature (TSUULL)", "uz", None),
    ("019d0172-8ff7-7c59-9ac1-22381a320eb2", "Tashkent Textile and Light Industry Institute (TTLII)", "uz", None),
    ("019cbc7c-776c-7c0f-8689-ddd17820474d", "Tashkent University of Applied Sciences (UTAS)", "en", None),
    ("019d0172-8fc6-773b-a03f-42da40fb6cd8", "Tashkent University of Architecture and Construction (TUAC)", "uz", None),
    ("019d0172-8fdf-733b-bb4c-fdec90826008", "Tashkent University of Economics and technologies (TUET)", "uz", None),
    ("019d0172-8fc8-7fb1-a623-cc7f21bf0758", "Tashkent University of Information Technologies (TUIT)", "uz", None),
    ("019d0172-8fdc-7bc9-bdf1-ab9f52a0f959", "Tashkent University of Social Innovation (TUSI)", "uz", None),
    ("019d0172-8fb9-7f9e-bb80-da38a595cfd0", "Tashkent University of Technology (TUT)", "uz", None),
    ("019d0172-8fba-72a5-820a-e9c2d6fea60c", "TEAM University (TEAM)", "uz", None),
    ("019d0172-8fbd-7326-a1bf-bca42a52e763", "Termiz State Pedagogical Institute (TSPI)", "uz", None),
    ("019d0172-8fbb-706d-aef7-a6f04eb04fa3", "Termiz State University of Engineering and Agrotechnology (TSUEAT)", "uz", None),
    ("019d0172-8fbe-787a-ac79-bc337fab375b", "Termiz State University (TerSU)", "uz", None),
    ("019d0172-8fc0-764f-aaf5-60dd9e98e531", "Termiz University of Economics and Service (TUES)", "uz", None),
    ("019d0172-8fc1-7843-9002-f8750ff09ca9", "The OXUS University (OXUS)", "uz", None),
    ("019d0172-8f45-74cb-b710-4b44d10e4727", "The University of World Economy and Diplomacy (UWED)", "uz", None),
    ("019d0172-8fc2-7726-a94e-2ae5553ee26a", "TMC INSTITUTI (TMC)", "uz", None),
    ("019d0172-8ff4-776b-badb-00569c8aa90b", "TOBB University of Economics and Technology in Tashkent (TOBB-TB)", "en", None),
    ("019d0172-8fd5-7887-a521-fd066831cb2a", "Toshkent davlat tibbiyot universiteti Termiz filiali (TMA-TB)", "uz", None),
    ("019d0172-8fd3-79a8-a5d3-897b02662391", "Toshkent davlat tibbiyot universiteti (TMA/TSMU)", "uz", None),
    ("019d0172-8ffb-7428-826e-0fcf6eda61f5", "Turan International University (TIUT)", "uz", None),
    ("019d0172-8ff3-7b87-9e75-e86b6c6002da", "Turin Polytechnic University in Tashkent (TTPU)", "en", None),
    ("019d0172-8fe7-7975-91df-3db04bdbce90", "University of Adju in Tashkent (Ajou-TB)", "en", None),
    ("019d0172-9001-7ef8-b399-96fb204b55dd", "University of Business and Science (UBS)", "uz", None),
    ("019d0172-8f96-710a-b8b9-2d1be718fbe7", "University of digital economy and agro-technologies (UDEA)", "uz", None),
    ("019d0172-8f42-75eb-a3df-c46046c0ee7b", "University of economics and pedagogy (UEP)", "uz", None),
    ("019d0172-8f07-70d8-81b3-2a1f01ddf44d", "University of Exact and Social Sciences (UESS)", "uz", None),
    ("019d0172-8f35-7181-a0de-bd87508d9434", "University of Geological Sciences (UGS)", "uz", None),
    ("019d0172-8f09-7aaa-b798-cd4cc01e18c4", "UNIVERSITY OF INFORMATION TECHNOLOGY AND MANAGEMENT (UITM)", "uz", None),
    ("019d0172-8f7d-722a-8ae7-3f5ecb5d4cf1", "University of Journalism and Mass Communications of Uzbekistan (UJMU)", "uz", None),
    ("019d0172-9005-77a1-9bd6-3b24a5d81808", "University of Management and Future Technologies (UMFT)", "uz", None),
    ("019d0172-8f29-708f-aa41-361447a2f908", "University of science and technologies (UST)", "uz", None),
    ("019d0172-8fff-7dc4-9d9e-84f8b1ed68eb", "University of Turon (TuronU)", "uz", None),
    ("019d0172-8f6c-7aa8-aeb8-0e716b048169", "Urganch branch of the State Academy of Choreography of Uzbekistan (SACU-UB)", "uz", None),
    ("019d0172-9009-7bcb-999c-4b028115ffcf", "Urganch davlat tibbiyot instituti (UrSMI)", "uz", None),
    ("019d0172-900e-78f5-95d2-1969c64e22a2", "Urganch RANCH University of Technology (RANCH)", "uz", None),
    ("019d0172-900b-7956-b6f5-f37a70ad8793", "Urganch State University (UrSU)", "uz", None),
    ("019d0172-9007-722f-8be9-6c4f089c4f33", "Urgench State Pedagogical Institute (UrSPI)", "uz", None),
    ("019d0172-900d-7993-b332-221502c13f3b", "Urgench University Of Innovation (UrUI)", "uz", None),
    ("019d0172-8fb0-7eee-8aec-4d8b7a1c8073", "Urgut branch of Samarkand State University named after Sharaf Rashidov (SamSU-UrB)", "uz", None),
    ("019d0172-8f84-77b8-b8d0-d8c41fbaaf7f", "Uzbek-French university (UFU)", "uz", None),
    ("019d0172-8f81-7ff5-bdc8-1c320ebcabe9", "Uzbekistan International Academy of Islamic Studies (IAISU)", "uz", None),
    ("019d0172-8f7f-7561-81c6-e535f72789f2", "Uzbekistan National Pedagogical University (UzSPU (Nizami))", "uz", None),
    ("019d0172-8f7b-7253-814d-f5d40b68501d", "Uzbekistan State Sports Academy (UzSSA)", "uz", None),
    ("019d0172-8f74-76dc-90fd-b5fdb7da2170", "Uzbekistan State University of Physical Education and Sports (UzSPESU)", "uz", None),
    ("019d0172-8f73-767c-a8b9-80e63deb2d00", "Uzbekistan State University of World Languages (UzSWLU)", "uz", None),
    ("019d0172-8fe3-78c4-b05d-04b811a11050", "Yangiyer branch of the Tashkent Institute of Chemical Technology (TICT-YB)", "uz", None),
    ("019d0172-9020-71ba-846a-016f2c3c9e60", "Zarmed University (Zarmed)", "uz", None),
]

# rq-scheduler polls every 5s (see docker-compose); pad the wait after a
# batch so we don't start the next one before the last delayed job fires.
SCHEDULER_POLL_BUFFER_SECONDS = 15


class Command(BaseCommand):
    help = (
        "Send the manual email campaign to one university (--university-id) "
        "or every configured university (--all), paced at a fixed global "
        "rate (--rate-per-hour). Runs in-process against the database and "
        "RQ directly -- no HTTP, no login, no cookies."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--template-type", required=True,
            help="EmailTemplate.template_type, e.g. preview_prod",
        )
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument(
            "--university-id",
            help="Send to just this EduPartner UUID (must be one of the configured UNIVERSITIES)",
        )
        target.add_argument(
            "--all", action="store_true",
            help="Send to every configured university, in list order",
        )
        target.add_argument(
            "--no-university", action="store_true",
            help="Send to active candidates with no educational partner assigned at all "
                 "(not covered by --all, which only ever targets the configured UNIVERSITIES list)",
        )
        parser.add_argument(
            "--language", choices=["uz", "ru", "en"],
            help="Only used with --no-university (there's no per-university signal for this "
                 "group). Omit to use each candidate's own preferred_language, falling back "
                 "to uz.",
        )
        parser.add_argument(
            "--rate-per-hour", type=float, default=40.0,
            help="Global send rate across the whole run (default: 40)",
        )
        parser.add_argument(
            "--vacancy-limit", type=int, default=5,
            help="Vacancies per email, 1-7 (default: 5)",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print the plan and exit without sending anything",
        )

    def handle(self, *args, **options):
        template_type = options["template_type"]
        rate_per_hour = options["rate_per_hour"]
        vacancy_limit = options["vacancy_limit"]
        dry_run = options["dry_run"]

        if rate_per_hour <= 0:
            raise CommandError("--rate-per-hour must be > 0")
        interval_seconds = 3600.0 / rate_per_hour
        service = ManualEmailCampaignService()

        self.stdout.write(self.style.NOTICE(
            f"Global rate: {rate_per_hour:.2f} emails/hour -> {interval_seconds:.1f}s between each email"
        ))

        if options["no_university"]:
            language = options.get("language")
            self.stdout.write(
                "Targeting active candidates with no educational partner assigned "
                f"(language={language or 'per-candidate preferred_language, falling back to uz'})"
            )
            if dry_run:
                self.stdout.write(self.style.NOTICE("\n--- DRY RUN: no emails will be sent ---"))
                self.stdout.write("\nRe-run without --dry-run to actually send.")
                return

            payload: dict[str, Any] = {
                "template_type": template_type,
                "audience": "candidates",
                "emails": [],
                "edupartner_ids": [],
                "no_university_only": True,
                "vacancy_limit": vacancy_limit,
                "cooldown_seconds": int(round(interval_seconds)),
            }
            if language:
                payload["language"] = language
            self._send_batch(service, "candidates with no university", payload, interval_seconds)
            self.stdout.write(self.style.SUCCESS("Done."))
            return

        if options["university_id"]:
            targets = [u for u in UNIVERSITIES if u[0] == options["university_id"]]
            if not targets:
                raise CommandError(
                    f"University id {options['university_id']!r} is not in the configured "
                    f"UNIVERSITIES list in this command."
                )
        else:
            targets = UNIVERSITIES

        self.stdout.write(f"Targeting {len(targets)} universit{'y' if len(targets) == 1 else 'ies'}")

        if dry_run:
            self.stdout.write(self.style.NOTICE("\n--- DRY RUN: no emails will be sent ---"))
            for edupartner_id, name, language, limit in targets:
                self.stdout.write(f"  [would send] {name}: language={language}, recipient_limit={limit or 'none'}")
            self.stdout.write("\nRe-run without --dry-run to actually send.")
            return

        for edupartner_id, name, language, limit in targets:
            payload = {
                "template_type": template_type,
                "audience": "candidates",
                "emails": [],
                "edupartner_ids": [edupartner_id],
                "language": language,
                "vacancy_limit": vacancy_limit,
                "cooldown_seconds": int(round(interval_seconds)),
            }
            if limit:
                payload["recipient_limit"] = limit
            self._send_batch(service, name, payload, interval_seconds)

        self.stdout.write(self.style.SUCCESS("Done."))

    def _send_batch(self, service, label, payload, interval_seconds):
        self.stdout.write(f"Sending to {label} (language={payload.get('language', 'per-candidate')})")

        try:
            result = service.send(payload)
        except Exception as exc:
            logger.exception("Failed to send campaign to %s", label)
            self.stderr.write(self.style.ERROR(f"  Failed: {exc}"))
            return

        sent_count = result.get("sent_count", 0)
        skipped_count = result.get("skipped_count", 0)
        failed_count = result.get("failed_count", 0)
        self.stdout.write(
            f"  recipient_count={result.get('recipient_count')} sent_count={sent_count} "
            f"skipped_count={skipped_count} failed_count={failed_count}"
        )

        if sent_count > 1:
            wait_seconds = (sent_count - 1) * interval_seconds + SCHEDULER_POLL_BUFFER_SECONDS
            self.stdout.write(f"  Waiting {wait_seconds:.0f}s for this batch to finish sending...")
            time.sleep(wait_seconds)
        elif sent_count == 1:
            time.sleep(interval_seconds)
