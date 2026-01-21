"""
Generate HTML report of bookings by country
"""

import mysql.connector
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

def generate_html_report():
    """Generate HTML report of country statistics"""
    
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME'),
        'port': int(os.getenv('DB_PORT', 3306))
    }
    
    print(f"\nConnecting to database: {db_config['database']} at {db_config['host']}")
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Get country statistics
        cursor.execute("""
            SELECT 
                country, 
                countryName, 
                countryNameNL,
                countryRegion,
                COUNT(*) as bookings
            FROM vw_bnb_total 
            WHERE country IS NOT NULL
            GROUP BY country, countryName, countryNameNL, countryRegion
            ORDER BY COUNT(*) DESC
        """)
        
        country_data = cursor.fetchall()
        
        # Get total bookings
        cursor.execute("SELECT COUNT(*) FROM vw_bnb_total WHERE country IS NOT NULL")
        total_bookings = cursor.fetchone()[0]
        
        # Get bookings by region
        cursor.execute("""
            SELECT 
                countryRegion,
                COUNT(*) as bookings
            FROM vw_bnb_total
            WHERE countryRegion IS NOT NULL
            GROUP BY countryRegion
            ORDER BY bookings DESC
        """)
        
        region_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Generate HTML
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bookings by Country Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}
        
        .header .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}
        
        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 12px rgba(0,0,0,0.15);
        }}
        
        .stat-card .number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        
        .stat-card .label {{
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section {{
            margin-bottom: 50px;
        }}
        
        .section h2 {{
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            font-size: 1.8em;
        }}
        
        .table-container {{
            overflow-x: auto;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
        }}
        
        thead {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        
        th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85em;
            letter-spacing: 1px;
        }}
        
        th.number {{
            text-align: right;
        }}
        
        tbody tr {{
            border-bottom: 1px solid #e0e0e0;
            transition: background-color 0.2s ease;
        }}
        
        tbody tr:hover {{
            background-color: #f5f5f5;
        }}
        
        tbody tr:nth-child(even) {{
            background-color: #fafafa;
        }}
        
        tbody tr:nth-child(even):hover {{
            background-color: #f0f0f0;
        }}
        
        td {{
            padding: 12px 15px;
            color: #333;
        }}
        
        td.number {{
            text-align: right;
            font-weight: 600;
            color: #667eea;
        }}
        
        .flag {{
            font-size: 1.5em;
            margin-right: 8px;
        }}
        
        .country-code {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 600;
            margin-right: 8px;
        }}
        
        .percentage {{
            color: #999;
            font-size: 0.9em;
            margin-left: 5px;
        }}
        
        .region-badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 500;
            background: #e3f2fd;
            color: #1976d2;
        }}
        
        .region-badge.europe {{ background: #e8f5e9; color: #388e3c; }}
        .region-badge.asia {{ background: #fff3e0; color: #f57c00; }}
        .region-badge.africa {{ background: #fce4ec; color: #c2185b; }}
        .region-badge.americas {{ background: #e1f5fe; color: #0277bd; }}
        .region-badge.oceania {{ background: #f3e5f5; color: #7b1fa2; }}
        .region-badge.middle-east {{ background: #fff9c4; color: #f57f17; }}
        
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 0.9em;
        }}
        
        .chart-bar {{
            height: 20px;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            margin: 5px 0;
            transition: width 0.5s ease;
        }}
        
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            
            .container {{
                box-shadow: none;
            }}
            
            .stat-card:hover,
            tbody tr:hover {{
                transform: none;
                background-color: inherit;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌍 Bookings by Country</h1>
            <div class="subtitle">Guest Origin Analysis Report</div>
            <div class="subtitle">Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}</div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="number">{total_bookings}</div>
                <div class="label">Total Bookings</div>
            </div>
            <div class="stat-card">
                <div class="number">{len(country_data)}</div>
                <div class="label">Countries</div>
            </div>
            <div class="stat-card">
                <div class="number">{len(region_data)}</div>
                <div class="label">Regions</div>
            </div>
            <div class="stat-card">
                <div class="number">{country_data[0][1] if country_data else 'N/A'}</div>
                <div class="label">Top Country</div>
            </div>
        </div>
        
        <div class="content">
            <!-- Bookings by Region -->
            <div class="section">
                <h2>📊 Bookings by Region</h2>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Region</th>
                                <th class="number">Bookings</th>
                                <th class="number">Percentage</th>
                                <th>Distribution</th>
                            </tr>
                        </thead>
                        <tbody>
"""
        
        # Add region data
        for region, bookings in region_data:
            percentage = (bookings / total_bookings * 100)
            bar_width = percentage
            region_class = region.lower().replace(' ', '-').replace('/', '-')
            html_content += f"""
                            <tr>
                                <td><span class="region-badge {region_class}">{region}</span></td>
                                <td class="number">{bookings:,}</td>
                                <td class="number">{percentage:.1f}%</td>
                                <td><div class="chart-bar" style="width: {bar_width}%;"></div></td>
                            </tr>
"""
        
        html_content += """
                        </tbody>
                    </table>
                </div>
            </div>
            
            <!-- Bookings by Country -->
            <div class="section">
                <h2>🗺️ Bookings by Country</h2>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Rank</th>
                                <th>Country</th>
                                <th>Dutch Name</th>
                                <th>Region</th>
                                <th class="number">Bookings</th>
                                <th class="number">Percentage</th>
                            </tr>
                        </thead>
                        <tbody>
"""
        
        # Add country data
        for rank, (code, name, name_nl, region, bookings) in enumerate(country_data, 1):
            percentage = (bookings / total_bookings * 100)
            region_class = region.lower().replace(' ', '-').replace('/', '-') if region else ''
            html_content += f"""
                            <tr>
                                <td><strong>#{rank}</strong></td>
                                <td>
                                    <span class="country-code">{code}</span>
                                    {name}
                                </td>
                                <td>{name_nl or 'N/A'}</td>
                                <td><span class="region-badge {region_class}">{region or 'N/A'}</span></td>
                                <td class="number">{bookings:,}</td>
                                <td class="number">{percentage:.1f}%</td>
                            </tr>
"""
        
        html_content += f"""
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>Report generated from booking database • Total bookings with country data: {total_bookings:,}</p>
            <p>Data includes both actual and planned bookings</p>
        </div>
    </div>
</body>
</html>
"""
        
        # Save HTML file
        output_file = Path(__file__).parent.parent / 'reports' / 'country_bookings_report.html'
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"\n✓ HTML report generated successfully!")
        print(f"  Location: {output_file}")
        print(f"  Total bookings: {total_bookings:,}")
        print(f"  Countries: {len(country_data)}")
        print(f"  Regions: {len(region_data)}")
        
        # Also save to Downloads folder
        downloads_file = Path.home() / 'Downloads' / 'country_bookings_report.html'
        with open(downloads_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"  Also saved to: {downloads_file}")
        
        print("\n" + "="*60)
        print("✓ Report generation complete!")
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
    generate_html_report()
