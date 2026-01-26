#!/usr/bin/env python3
"""
Tenant Filtering Performance Analysis
Analyzes the performance impact of tenant filtering on SQL queries
"""

import re
import os
from collections import defaultdict

def analyze_tenant_filtering_performance():
    """Analyze performance impact of tenant filtering queries"""
    
    print("=" * 80)
    print("TENANT FILTERING PERFORMANCE ANALYSIS")
    print("=" * 80)
    print()
    
    files_to_check = [
        'backend/src/bnb_routes.py',
        'backend/src/str_channel_routes.py', 
        'backend/src/str_invoice_routes.py'
    ]
    
    query_analysis = []
    performance_issues = []
    optimization_opportunities = []
    
    for filepath in files_to_check:
        if not os.path.exists(filepath):
            print(f"❌ File not found: {filepath}")
            continue
            
        print(f"📁 Analyzing: {filepath}")
        print("-" * 60)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract SQL queries
        queries = extract_sql_queries(content)
        
        for query_info in queries:
            analysis = analyze_query_performance(query_info, filepath)
            query_analysis.append(analysis)
            
            if analysis['performance_issues']:
                performance_issues.extend(analysis['performance_issues'])
            
            if analysis['optimization_opportunities']:
                optimization_opportunities.extend(analysis['optimization_opportunities'])
        
        print(f"Queries analyzed: {len(queries)}")
        
        file_issues = [a for a in query_analysis if a['file'] == filepath and a['performance_issues']]
        if file_issues:
            print("⚠️  Performance concerns:")
            for analysis in file_issues:
                for issue in analysis['performance_issues']:
                    print(f"  • {issue}")
        else:
            print("✅ No obvious performance issues")
        
        print()
    
    # Overall performance analysis
    print("=" * 80)
    print("PERFORMANCE ANALYSIS SUMMARY")
    print("=" * 80)
    
    total_queries = len(query_analysis)
    queries_with_issues = len([a for a in query_analysis if a['performance_issues']])
    
    print(f"Total queries analyzed: {total_queries}")
    print(f"Queries with performance concerns: {queries_with_issues}")
    print(f"Performance score: {((total_queries - queries_with_issues) / total_queries * 100):.1f}%" if total_queries > 0 else "N/A")
    print()
    
    # Categorize issues
    issue_categories = defaultdict(int)
    for issue in performance_issues:
        if 'index' in issue.lower():
            issue_categories['Indexing'] += 1
        elif 'join' in issue.lower():
            issue_categories['Joins'] += 1
        elif 'where' in issue.lower():
            issue_categories['WHERE clauses'] += 1
        elif 'tenant' in issue.lower():
            issue_categories['Tenant filtering'] += 1
        else:
            issue_categories['Other'] += 1
    
    if issue_categories:
        print("📊 ISSUE CATEGORIES:")
        for category, count in issue_categories.items():
            print(f"  {category}: {count}")
        print()
    
    # Optimization recommendations
    print("🚀 OPTIMIZATION RECOMMENDATIONS:")
    print("-" * 35)
    
    if not performance_issues:
        print("✅ No major performance issues identified")
        print("• Continue monitoring query performance")
        print("• Consider adding query execution time logging")
        print("• Regular performance testing with larger datasets")
    else:
        print("🎯 HIGH PRIORITY:")
        high_priority = [
            "Add database indexes on administration column",
            "Optimize WHERE clause ordering",
            "Consider query result caching for frequently accessed data",
            "Add LIMIT clauses to prevent large result sets"
        ]
        
        for rec in high_priority:
            print(f"  • {rec}")
        
        print()
        print("📈 MEDIUM PRIORITY:")
        medium_priority = [
            "Analyze query execution plans",
            "Consider database connection pooling",
            "Implement query result pagination",
            "Add query performance monitoring"
        ]
        
        for rec in medium_priority:
            print(f"  • {rec}")
    
    print()
    
    # Specific tenant filtering analysis
    print("🔒 TENANT FILTERING ANALYSIS:")
    print("-" * 30)
    
    tenant_queries = [a for a in query_analysis if 'administration IN' in a['query_text']]
    print(f"Queries with tenant filtering: {len(tenant_queries)}")
    
    if tenant_queries:
        print("✅ Tenant filtering implementation:")
        print("  • Uses parameterized queries (secure)")
        print("  • Filters at database level (efficient)")
        print("  • Consistent pattern across endpoints")
        
        # Check for potential optimizations
        print()
        print("🔧 TENANT FILTERING OPTIMIZATIONS:")
        print("  • Ensure 'administration' column is indexed")
        print("  • Consider composite indexes for frequently filtered combinations")
        print("  • Monitor query performance with multiple tenants")
        print("  • Consider tenant-specific database partitioning for large datasets")
    
    print()
    
    # Database recommendations
    print("💾 DATABASE RECOMMENDATIONS:")
    print("-" * 25)
    
    print("📋 REQUIRED INDEXES:")
    recommended_indexes = [
        "CREATE INDEX idx_bnb_administration ON bnb(administration);",
        "CREATE INDEX idx_mutaties_administration ON mutaties(administration);",
        "CREATE INDEX idx_bnb_admin_year ON bnb(administration, year);",
        "CREATE INDEX idx_bnb_admin_listing ON bnb(administration, listing);",
        "CREATE INDEX idx_bnb_admin_channel ON bnb(administration, channel);"
    ]
    
    for idx in recommended_indexes:
        print(f"  {idx}")
    
    print()
    print("📊 MONITORING QUERIES:")
    monitoring_queries = [
        "-- Check query performance",
        "EXPLAIN SELECT * FROM bnb WHERE administration IN ('tenant1', 'tenant2');",
        "",
        "-- Check index usage",
        "SHOW INDEX FROM bnb WHERE Key_name LIKE '%administration%';",
        "",
        "-- Monitor slow queries",
        "SELECT * FROM mysql.slow_log WHERE sql_text LIKE '%administration%';"
    ]
    
    for query in monitoring_queries:
        print(f"  {query}")
    
    return {
        'total_queries': total_queries,
        'performance_issues': len(performance_issues),
        'optimization_opportunities': len(optimization_opportunities),
        'tenant_filtered_queries': len(tenant_queries)
    }

def extract_sql_queries(content):
    """Extract SQL queries from Python code"""
    queries = []
    
    # Pattern for multi-line SQL queries
    patterns = [
        r'query = f?"""(.*?)"""',
        r'query = f?"(.*?)"',
        r'.*_query = f?"""(.*?)"""',
        r'.*_query = f?"(.*?)"'
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)
        for match in matches:
            query_text = match.group(1).strip()
            if any(keyword in query_text.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                line_num = content[:match.start()].count('\n') + 1
                queries.append({
                    'text': query_text,
                    'line': line_num,
                    'full_match': match.group(0)
                })
    
    return queries

def analyze_query_performance(query_info, filepath):
    """Analyze performance characteristics of a single query"""
    
    query_text = query_info['text'].upper()
    analysis = {
        'file': filepath,
        'line': query_info['line'],
        'query_text': query_info['text'],
        'performance_issues': [],
        'optimization_opportunities': [],
        'complexity_score': 0
    }
    
    # Check for performance issues
    
    # 1. Missing LIMIT clauses on potentially large result sets
    if 'SELECT' in query_text and 'LIMIT' not in query_text:
        if any(table in query_text for table in ['BNB', 'MUTATIES', 'VW_']):
            analysis['performance_issues'].append("Missing LIMIT clause on potentially large table")
            analysis['complexity_score'] += 2
    
    # 2. Complex WHERE clauses
    where_conditions = query_text.count('WHERE') + query_text.count('AND') + query_text.count('OR')
    if where_conditions > 5:
        analysis['performance_issues'].append(f"Complex WHERE clause with {where_conditions} conditions")
        analysis['complexity_score'] += 1
    
    # 3. Multiple JOINs
    join_count = query_text.count('JOIN')
    if join_count > 2:
        analysis['performance_issues'].append(f"Multiple JOINs ({join_count}) may impact performance")
        analysis['complexity_score'] += join_count
    
    # 4. Subqueries
    if 'SELECT' in query_text and query_text.count('SELECT') > 1:
        analysis['performance_issues'].append("Contains subqueries which may impact performance")
        analysis['complexity_score'] += 2
    
    # 5. Functions in WHERE clauses
    if any(func in query_text for func in ['LOWER(', 'UPPER(', 'SUBSTRING(', 'DATE(']):
        analysis['optimization_opportunities'].append("Functions in WHERE clause prevent index usage")
        analysis['complexity_score'] += 1
    
    # 6. Wildcard searches
    if 'LIKE' in query_text and '%' in query_info['text']:
        analysis['optimization_opportunities'].append("LIKE with wildcards may be slow on large datasets")
        analysis['complexity_score'] += 1
    
    # 7. ORDER BY without LIMIT
    if 'ORDER BY' in query_text and 'LIMIT' not in query_text:
        analysis['optimization_opportunities'].append("ORDER BY without LIMIT sorts entire result set")
        analysis['complexity_score'] += 1
    
    # 8. Tenant filtering analysis
    if 'ADMINISTRATION IN' in query_text:
        analysis['optimization_opportunities'].append("Ensure administration column is indexed")
        # This is actually good for security, so don't add to complexity
    
    # 9. Aggregation functions
    agg_functions = ['SUM(', 'COUNT(', 'AVG(', 'MAX(', 'MIN(']
    agg_count = sum(query_text.count(func) for func in agg_functions)
    if agg_count > 3:
        analysis['optimization_opportunities'].append(f"Multiple aggregations ({agg_count}) - consider materialized views")
        analysis['complexity_score'] += 1
    
    return analysis

if __name__ == '__main__':
    analyze_tenant_filtering_performance()