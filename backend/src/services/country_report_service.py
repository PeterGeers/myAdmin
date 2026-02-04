"""
Country Bookings Report Generation Service

Handles the generation of HTML reports showing guest origin statistics
by country and region.
"""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def get_country_report_data(user_tenants):
    """
    Fetch country booking data from database
    
    Args:
        user_tenants: List of tenant IDs the user has access to
        
    Returns:
        tuple: (country_data, region_data, total_bookings)
    """
    from database import DatabaseManager
    
    db = DatabaseManager(test_mode=False)
    connection = db.get_connection()
    cursor = connection.cursor()
    
    # Build tenant filter
    placeholders = ', '.join(['%s'] * len(user_tenants))
    
    # Get country statistics with JOIN to countries table
    cursor.execute(f"""
        SELECT 
            v.country, 
            c.name as countryName, 
            c.name_nl as countryNameNL,
            c.region as countryRegion,
            COUNT(*) as bookings
        FROM vw_bnb_total v
        LEFT JOIN countries c ON v.country = c.code
        WHERE v.country IS NOT NULL AND v.administration IN ({placeholders})
        GROUP BY v.country, c.name, c.name_nl, c.region
        ORDER BY COUNT(*) DESC
    """, user_tenants)
    
    country_data = cursor.fetchall()
    
    # Get total bookings
    cursor.execute(f"""
        SELECT COUNT(*) FROM vw_bnb_total 
        WHERE country IS NOT NULL AND administration IN ({placeholders})
    """, user_tenants)
    total_bookings = cursor.fetchone()[0]
    
    # Get bookings by region
    cursor.execute(f"""
        SELECT 
            c.region as countryRegion,
            COUNT(*) as bookings
        FROM vw_bnb_total v
        LEFT JOIN countries c ON v.country = c.code
        WHERE c.region IS NOT NULL AND v.administration IN ({placeholders})
        GROUP BY c.region
        ORDER BY bookings DESC
    """, user_tenants)
    
    region_data = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return country_data, region_data, total_bookings


def generate_country_report_html(country_data, region_data, total_bookings):
    """
    Generate HTML content for country bookings report
    
    Args:
        country_data: List of tuples (country_code, name, name_nl, region, bookings)
        region_data: List of tuples (region, bookings)
        total_bookings: Total number of bookings
        
    Returns:
        str: Complete HTML content for the report
    """
    
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
    
    return html_content


def save_report(html_content, output_filename='country_bookings_report.html'):
    """
    Save HTML report to file system
    
    Args:
        html_content: HTML string to save
        output_filename: Name of the output file
        
    Returns:
        Path: Path to the saved file
    """
    # Determine the reports directory (relative to this service file)
    output_dir = Path(__file__).parent.parent.parent / 'reports'
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / output_filename
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f'Country report saved: {output_file}')
    
    return output_file
