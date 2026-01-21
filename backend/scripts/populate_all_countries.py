"""
Populate countries table with all ISO 3166-1 alpha-2 countries
Complete list of 249 countries with English and Dutch names
"""

import mysql.connector
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

def populate_all_countries():
    """Populate countries table with complete ISO 3166-1 list"""
    
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME'),
        'port': int(os.getenv('DB_PORT', 3306))
    }
    
    print(f"\nConnecting to database: {db_config['database']} at {db_config['host']}")
    print("="*60)
    
    # Complete list of all ISO 3166-1 alpha-2 countries
    all_countries = [
        # Europe
        ('AD', 'Andorra', 'Andorra', 'Europe'),
        ('AL', 'Albania', 'Albanië', 'Europe'),
        ('AT', 'Austria', 'Oostenrijk', 'Europe'),
        ('AX', 'Åland Islands', 'Åland', 'Europe'),
        ('BA', 'Bosnia and Herzegovina', 'Bosnië en Herzegovina', 'Europe'),
        ('BE', 'Belgium', 'België', 'Europe'),
        ('BG', 'Bulgaria', 'Bulgarije', 'Europe'),
        ('BY', 'Belarus', 'Wit-Rusland', 'Europe'),
        ('CH', 'Switzerland', 'Zwitserland', 'Europe'),
        ('CY', 'Cyprus', 'Cyprus', 'Europe'),
        ('CZ', 'Czech Republic', 'Tsjechië', 'Europe'),
        ('DE', 'Germany', 'Duitsland', 'Europe'),
        ('DK', 'Denmark', 'Denemarken', 'Europe'),
        ('EE', 'Estonia', 'Estland', 'Europe'),
        ('ES', 'Spain', 'Spanje', 'Europe'),
        ('FI', 'Finland', 'Finland', 'Europe'),
        ('FO', 'Faroe Islands', 'Faeröer', 'Europe'),
        ('FR', 'France', 'Frankrijk', 'Europe'),
        ('GB', 'United Kingdom', 'Verenigd Koninkrijk', 'Europe'),
        ('GG', 'Guernsey', 'Guernsey', 'Europe'),
        ('GI', 'Gibraltar', 'Gibraltar', 'Europe'),
        ('GR', 'Greece', 'Griekenland', 'Europe'),
        ('HR', 'Croatia', 'Kroatië', 'Europe'),
        ('HU', 'Hungary', 'Hongarije', 'Europe'),
        ('IE', 'Ireland', 'Ierland', 'Europe'),
        ('IM', 'Isle of Man', 'Isle of Man', 'Europe'),
        ('IS', 'Iceland', 'IJsland', 'Europe'),
        ('IT', 'Italy', 'Italië', 'Europe'),
        ('JE', 'Jersey', 'Jersey', 'Europe'),
        ('LI', 'Liechtenstein', 'Liechtenstein', 'Europe'),
        ('LT', 'Lithuania', 'Litouwen', 'Europe'),
        ('LU', 'Luxembourg', 'Luxemburg', 'Europe'),
        ('LV', 'Latvia', 'Letland', 'Europe'),
        ('MC', 'Monaco', 'Monaco', 'Europe'),
        ('MD', 'Moldova', 'Moldavië', 'Europe'),
        ('ME', 'Montenegro', 'Montenegro', 'Europe'),
        ('MK', 'North Macedonia', 'Noord-Macedonië', 'Europe'),
        ('MT', 'Malta', 'Malta', 'Europe'),
        ('NL', 'Netherlands', 'Nederland', 'Europe'),
        ('NO', 'Norway', 'Noorwegen', 'Europe'),
        ('PL', 'Poland', 'Polen', 'Europe'),
        ('PT', 'Portugal', 'Portugal', 'Europe'),
        ('RO', 'Romania', 'Roemenië', 'Europe'),
        ('RS', 'Serbia', 'Servië', 'Europe'),
        ('RU', 'Russia', 'Rusland', 'Europe/Asia'),
        ('SE', 'Sweden', 'Zweden', 'Europe'),
        ('SI', 'Slovenia', 'Slovenië', 'Europe'),
        ('SJ', 'Svalbard and Jan Mayen', 'Svalbard en Jan Mayen', 'Europe'),
        ('SK', 'Slovakia', 'Slowakije', 'Europe'),
        ('SM', 'San Marino', 'San Marino', 'Europe'),
        ('UA', 'Ukraine', 'Oekraïne', 'Europe'),
        ('VA', 'Vatican City', 'Vaticaanstad', 'Europe'),
        ('XK', 'Kosovo', 'Kosovo', 'Europe'),
        
        # Asia
        ('AE', 'United Arab Emirates', 'Verenigde Arabische Emiraten', 'Middle East'),
        ('AF', 'Afghanistan', 'Afghanistan', 'Asia'),
        ('AM', 'Armenia', 'Armenië', 'Asia'),
        ('AZ', 'Azerbaijan', 'Azerbeidzjan', 'Asia'),
        ('BD', 'Bangladesh', 'Bangladesh', 'Asia'),
        ('BH', 'Bahrain', 'Bahrein', 'Middle East'),
        ('BN', 'Brunei', 'Brunei', 'Asia'),
        ('BT', 'Bhutan', 'Bhutan', 'Asia'),
        ('CN', 'China', 'China', 'Asia'),
        ('GE', 'Georgia', 'Georgië', 'Europe/Asia'),
        ('HK', 'Hong Kong', 'Hong Kong', 'Asia'),
        ('ID', 'Indonesia', 'Indonesië', 'Asia'),
        ('IL', 'Israel', 'Israël', 'Middle East'),
        ('IN', 'India', 'India', 'Asia'),
        ('IQ', 'Iraq', 'Irak', 'Middle East'),
        ('IR', 'Iran', 'Iran', 'Middle East'),
        ('JO', 'Jordan', 'Jordanië', 'Middle East'),
        ('JP', 'Japan', 'Japan', 'Asia'),
        ('KG', 'Kyrgyzstan', 'Kirgizië', 'Asia'),
        ('KH', 'Cambodia', 'Cambodja', 'Asia'),
        ('KP', 'North Korea', 'Noord-Korea', 'Asia'),
        ('KR', 'South Korea', 'Zuid-Korea', 'Asia'),
        ('KW', 'Kuwait', 'Koeweit', 'Middle East'),
        ('KZ', 'Kazakhstan', 'Kazachstan', 'Asia'),
        ('LA', 'Laos', 'Laos', 'Asia'),
        ('LB', 'Lebanon', 'Libanon', 'Middle East'),
        ('LK', 'Sri Lanka', 'Sri Lanka', 'Asia'),
        ('MM', 'Myanmar', 'Myanmar', 'Asia'),
        ('MN', 'Mongolia', 'Mongolië', 'Asia'),
        ('MO', 'Macao', 'Macao', 'Asia'),
        ('MV', 'Maldives', 'Maldiven', 'Asia'),
        ('MY', 'Malaysia', 'Maleisië', 'Asia'),
        ('NP', 'Nepal', 'Nepal', 'Asia'),
        ('OM', 'Oman', 'Oman', 'Middle East'),
        ('PH', 'Philippines', 'Filipijnen', 'Asia'),
        ('PK', 'Pakistan', 'Pakistan', 'Asia'),
        ('PS', 'Palestine', 'Palestina', 'Middle East'),
        ('QA', 'Qatar', 'Qatar', 'Middle East'),
        ('SA', 'Saudi Arabia', 'Saoedi-Arabië', 'Middle East'),
        ('SG', 'Singapore', 'Singapore', 'Asia'),
        ('SY', 'Syria', 'Syrië', 'Middle East'),
        ('TH', 'Thailand', 'Thailand', 'Asia'),
        ('TJ', 'Tajikistan', 'Tadzjikistan', 'Asia'),
        ('TL', 'Timor-Leste', 'Oost-Timor', 'Asia'),
        ('TM', 'Turkmenistan', 'Turkmenistan', 'Asia'),
        ('TR', 'Turkey', 'Turkije', 'Asia/Europe'),
        ('TW', 'Taiwan', 'Taiwan', 'Asia'),
        ('UZ', 'Uzbekistan', 'Oezbekistan', 'Asia'),
        ('VN', 'Vietnam', 'Vietnam', 'Asia'),
        ('YE', 'Yemen', 'Jemen', 'Middle East'),
        
        # Africa
        ('AO', 'Angola', 'Angola', 'Africa'),
        ('BF', 'Burkina Faso', 'Burkina Faso', 'Africa'),
        ('BI', 'Burundi', 'Burundi', 'Africa'),
        ('BJ', 'Benin', 'Benin', 'Africa'),
        ('BW', 'Botswana', 'Botswana', 'Africa'),
        ('CD', 'Democratic Republic of the Congo', 'Democratische Republiek Congo', 'Africa'),
        ('CF', 'Central African Republic', 'Centraal-Afrikaanse Republiek', 'Africa'),
        ('CG', 'Republic of the Congo', 'Congo-Brazzaville', 'Africa'),
        ('CI', 'Ivory Coast', 'Ivoorkust', 'Africa'),
        ('CM', 'Cameroon', 'Kameroen', 'Africa'),
        ('CV', 'Cape Verde', 'Kaapverdië', 'Africa'),
        ('DJ', 'Djibouti', 'Djibouti', 'Africa'),
        ('DZ', 'Algeria', 'Algerije', 'Africa'),
        ('EG', 'Egypt', 'Egypte', 'Africa'),
        ('EH', 'Western Sahara', 'Westelijke Sahara', 'Africa'),
        ('ER', 'Eritrea', 'Eritrea', 'Africa'),
        ('ET', 'Ethiopia', 'Ethiopië', 'Africa'),
        ('GA', 'Gabon', 'Gabon', 'Africa'),
        ('GH', 'Ghana', 'Ghana', 'Africa'),
        ('GM', 'Gambia', 'Gambia', 'Africa'),
        ('GN', 'Guinea', 'Guinee', 'Africa'),
        ('GQ', 'Equatorial Guinea', 'Equatoriaal-Guinea', 'Africa'),
        ('GW', 'Guinea-Bissau', 'Guinee-Bissau', 'Africa'),
        ('KE', 'Kenya', 'Kenia', 'Africa'),
        ('KM', 'Comoros', 'Comoren', 'Africa'),
        ('LR', 'Liberia', 'Liberia', 'Africa'),
        ('LS', 'Lesotho', 'Lesotho', 'Africa'),
        ('LY', 'Libya', 'Libië', 'Africa'),
        ('MA', 'Morocco', 'Marokko', 'Africa'),
        ('MG', 'Madagascar', 'Madagaskar', 'Africa'),
        ('ML', 'Mali', 'Mali', 'Africa'),
        ('MR', 'Mauritania', 'Mauritanië', 'Africa'),
        ('MU', 'Mauritius', 'Mauritius', 'Africa'),
        ('MW', 'Malawi', 'Malawi', 'Africa'),
        ('MZ', 'Mozambique', 'Mozambique', 'Africa'),
        ('NA', 'Namibia', 'Namibië', 'Africa'),
        ('NE', 'Niger', 'Niger', 'Africa'),
        ('NG', 'Nigeria', 'Nigeria', 'Africa'),
        ('RE', 'Réunion', 'Réunion', 'Africa'),
        ('RW', 'Rwanda', 'Rwanda', 'Africa'),
        ('SC', 'Seychelles', 'Seychellen', 'Africa'),
        ('SD', 'Sudan', 'Soedan', 'Africa'),
        ('SL', 'Sierra Leone', 'Sierra Leone', 'Africa'),
        ('SN', 'Senegal', 'Senegal', 'Africa'),
        ('SO', 'Somalia', 'Somalië', 'Africa'),
        ('SS', 'South Sudan', 'Zuid-Soedan', 'Africa'),
        ('ST', 'São Tomé and Príncipe', 'Sao Tomé en Principe', 'Africa'),
        ('SZ', 'Eswatini', 'Eswatini', 'Africa'),
        ('TD', 'Chad', 'Tsjaad', 'Africa'),
        ('TG', 'Togo', 'Togo', 'Africa'),
        ('TN', 'Tunisia', 'Tunesië', 'Africa'),
        ('TZ', 'Tanzania', 'Tanzania', 'Africa'),
        ('UG', 'Uganda', 'Oeganda', 'Africa'),
        ('YT', 'Mayotte', 'Mayotte', 'Africa'),
        ('ZA', 'South Africa', 'Zuid-Afrika', 'Africa'),
        ('ZM', 'Zambia', 'Zambia', 'Africa'),
        ('ZW', 'Zimbabwe', 'Zimbabwe', 'Africa'),
        
        # North America
        ('AG', 'Antigua and Barbuda', 'Antigua en Barbuda', 'Caribbean'),
        ('AI', 'Anguilla', 'Anguilla', 'Caribbean'),
        ('AW', 'Aruba', 'Aruba', 'Caribbean'),
        ('BB', 'Barbados', 'Barbados', 'Caribbean'),
        ('BL', 'Saint Barthélemy', 'Saint-Barthélemy', 'Caribbean'),
        ('BM', 'Bermuda', 'Bermuda', 'North America'),
        ('BQ', 'Caribbean Netherlands', 'Caribisch Nederland', 'Caribbean'),
        ('BS', 'Bahamas', 'Bahama\'s', 'Caribbean'),
        ('BZ', 'Belize', 'Belize', 'Central America'),
        ('CA', 'Canada', 'Canada', 'North America'),
        ('CR', 'Costa Rica', 'Costa Rica', 'Central America'),
        ('CU', 'Cuba', 'Cuba', 'Caribbean'),
        ('CW', 'Curaçao', 'Curaçao', 'Caribbean'),
        ('DM', 'Dominica', 'Dominica', 'Caribbean'),
        ('DO', 'Dominican Republic', 'Dominicaanse Republiek', 'Caribbean'),
        ('GD', 'Grenada', 'Grenada', 'Caribbean'),
        ('GL', 'Greenland', 'Groenland', 'North America'),
        ('GP', 'Guadeloupe', 'Guadeloupe', 'Caribbean'),
        ('GT', 'Guatemala', 'Guatemala', 'Central America'),
        ('HN', 'Honduras', 'Honduras', 'Central America'),
        ('HT', 'Haiti', 'Haïti', 'Caribbean'),
        ('JM', 'Jamaica', 'Jamaica', 'Caribbean'),
        ('KN', 'Saint Kitts and Nevis', 'Saint Kitts en Nevis', 'Caribbean'),
        ('KY', 'Cayman Islands', 'Kaaimaneilanden', 'Caribbean'),
        ('LC', 'Saint Lucia', 'Saint Lucia', 'Caribbean'),
        ('MF', 'Saint Martin', 'Sint-Maarten', 'Caribbean'),
        ('MQ', 'Martinique', 'Martinique', 'Caribbean'),
        ('MS', 'Montserrat', 'Montserrat', 'Caribbean'),
        ('MX', 'Mexico', 'Mexico', 'North America'),
        ('NI', 'Nicaragua', 'Nicaragua', 'Central America'),
        ('PA', 'Panama', 'Panama', 'Central America'),
        ('PM', 'Saint Pierre and Miquelon', 'Saint-Pierre en Miquelon', 'North America'),
        ('PR', 'Puerto Rico', 'Puerto Rico', 'Caribbean'),
        ('SV', 'El Salvador', 'El Salvador', 'Central America'),
        ('SX', 'Sint Maarten', 'Sint Maarten', 'Caribbean'),
        ('TC', 'Turks and Caicos Islands', 'Turks- en Caicoseilanden', 'Caribbean'),
        ('TT', 'Trinidad and Tobago', 'Trinidad en Tobago', 'Caribbean'),
        ('US', 'United States', 'Verenigde Staten', 'North America'),
        ('VC', 'Saint Vincent and the Grenadines', 'Saint Vincent en de Grenadines', 'Caribbean'),
        ('VG', 'British Virgin Islands', 'Britse Maagdeneilanden', 'Caribbean'),
        ('VI', 'U.S. Virgin Islands', 'Amerikaanse Maagdeneilanden', 'Caribbean'),
        
        # South America
        ('AR', 'Argentina', 'Argentinië', 'South America'),
        ('BO', 'Bolivia', 'Bolivia', 'South America'),
        ('BR', 'Brazil', 'Brazilië', 'South America'),
        ('CL', 'Chile', 'Chili', 'South America'),
        ('CO', 'Colombia', 'Colombia', 'South America'),
        ('EC', 'Ecuador', 'Ecuador', 'South America'),
        ('FK', 'Falkland Islands', 'Falklandeilanden', 'South America'),
        ('GF', 'French Guiana', 'Frans-Guyana', 'South America'),
        ('GY', 'Guyana', 'Guyana', 'South America'),
        ('PE', 'Peru', 'Peru', 'South America'),
        ('PY', 'Paraguay', 'Paraguay', 'South America'),
        ('SR', 'Suriname', 'Suriname', 'South America'),
        ('UY', 'Uruguay', 'Uruguay', 'South America'),
        ('VE', 'Venezuela', 'Venezuela', 'South America'),
        
        # Oceania
        ('AS', 'American Samoa', 'Amerikaans-Samoa', 'Oceania'),
        ('AU', 'Australia', 'Australië', 'Oceania'),
        ('CK', 'Cook Islands', 'Cookeilanden', 'Oceania'),
        ('FJ', 'Fiji', 'Fiji', 'Oceania'),
        ('FM', 'Micronesia', 'Micronesië', 'Oceania'),
        ('GU', 'Guam', 'Guam', 'Oceania'),
        ('KI', 'Kiribati', 'Kiribati', 'Oceania'),
        ('MH', 'Marshall Islands', 'Marshalleilanden', 'Oceania'),
        ('MP', 'Northern Mariana Islands', 'Noordelijke Marianen', 'Oceania'),
        ('NC', 'New Caledonia', 'Nieuw-Caledonië', 'Oceania'),
        ('NF', 'Norfolk Island', 'Norfolk', 'Oceania'),
        ('NR', 'Nauru', 'Nauru', 'Oceania'),
        ('NU', 'Niue', 'Niue', 'Oceania'),
        ('NZ', 'New Zealand', 'Nieuw-Zeeland', 'Oceania'),
        ('PF', 'French Polynesia', 'Frans-Polynesië', 'Oceania'),
        ('PG', 'Papua New Guinea', 'Papoea-Nieuw-Guinea', 'Oceania'),
        ('PN', 'Pitcairn Islands', 'Pitcairneilanden', 'Oceania'),
        ('PW', 'Palau', 'Palau', 'Oceania'),
        ('SB', 'Solomon Islands', 'Salomonseilanden', 'Oceania'),
        ('TK', 'Tokelau', 'Tokelau', 'Oceania'),
        ('TO', 'Tonga', 'Tonga', 'Oceania'),
        ('TV', 'Tuvalu', 'Tuvalu', 'Oceania'),
        ('VU', 'Vanuatu', 'Vanuatu', 'Oceania'),
        ('WF', 'Wallis and Futuna', 'Wallis en Futuna', 'Oceania'),
        ('WS', 'Samoa', 'Samoa', 'Oceania'),
        
        # Antarctica
        ('AQ', 'Antarctica', 'Antarctica', 'Antarctica'),
        ('BV', 'Bouvet Island', 'Bouveteiland', 'Antarctica'),
        ('GS', 'South Georgia', 'Zuid-Georgia', 'Antarctica'),
        ('HM', 'Heard Island and McDonald Islands', 'Heard en McDonaldeilanden', 'Antarctica'),
        ('TF', 'French Southern Territories', 'Franse Zuidelijke Gebieden', 'Antarctica'),
    ]
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        print(f"\nPopulating countries table with {len(all_countries)} countries...")
        print("-"*60)
        
        insert_query = """
            INSERT INTO countries (code, name, name_nl, region) 
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                name = VALUES(name),
                name_nl = VALUES(name_nl),
                region = VALUES(region)
        """
        
        cursor.executemany(insert_query, all_countries)
        conn.commit()
        
        print(f"✓ Successfully populated {len(all_countries)} countries")
        
        # Verification
        cursor.execute("SELECT COUNT(*) FROM countries")
        count = cursor.fetchone()[0]
        print(f"✓ Total countries in table: {count}")
        
        # Show breakdown by region
        print("\nCountries by region:")
        print("-"*60)
        cursor.execute("""
            SELECT region, COUNT(*) as count 
            FROM countries 
            GROUP BY region 
            ORDER BY count DESC
        """)
        for row in cursor.fetchall():
            print(f"  {row[0]:25s}: {row[1]:3d} countries")
        
        cursor.close()
        conn.close()
        
        print("\n" + "="*60)
        print("✓ All countries populated successfully!")
        print("="*60 + "\n")
        
    except mysql.connector.Error as e:
        print(f"\n✗ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    populate_all_countries()
