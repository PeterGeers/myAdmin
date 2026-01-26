#!/usr/bin/env python3
"""
SQL Injection Security Analysis for STR Reports
Analyzes all route files for potential SQL injection vulnerabilities
"""

import re
import os
import ast
from typing import List, Dict, Tuple

class SQLSecurityAnalyzer:
    def __init__(self):
        self.vulnerabilities = []
        self.safe_patterns = []
        self.warnings = []
        
    def analyze_file(self, filepath: str) -> Dict:
        """Analyze a Python file for SQL injection vulnerabilities"""
        results = {
            'file': filepath,
            'vulnerabilities': [],
            'warnings': [],
            'safe_queries': [],
            'total_queries': 0
        }
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find all SQL queries in the file
            queries = self._extract_sql_queries(content)
            results['total_queries'] = len(queries)
            
            for query_info in queries:
                analysis = self._analyze_query(query_info, content)
                
                if analysis['is_vulnerable']:
                    results['vulnerabilities'].append(analysis)
                elif analysis['has_warnings']:
                    results['warnings'].append(analysis)
                else:
                    results['safe_queries'].append(analysis)
                    
        except Exception as e:
            results['error'] = str(e)
            
        return results
    
    def _extract_sql_queries(self, content: str) -> List[Dict]:
        """Extract SQL queries from Python code"""
        queries = []
        
        # Pattern for multi-line SQL queries
        sql_patterns = [
            # Triple quoted strings that look like SQL
            r'"""[\s\S]*?SELECT[\s\S]*?"""',
            r"'''[\s\S]*?SELECT[\s\S]*?'''",
            # f-strings with SQL
            r'f"""[\s\S]*?SELECT[\s\S]*?"""',
            r"f'''[\s\S]*?SELECT[\s\S]*?'''",
            # Regular strings with SQL keywords
            r'"[^"]*(?:SELECT|INSERT|UPDATE|DELETE)[^"]*"',
            r"'[^']*(?:SELECT|INSERT|UPDATE|DELETE)[^']*'",
        ]
        
        for pattern in sql_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                query_text = match.group(0)
                line_num = content[:match.start()].count('\n') + 1
                
                queries.append({
                    'text': query_text,
                    'line': line_num,
                    'start': match.start(),
                    'end': match.end()
                })
        
        return queries
    
    def _analyze_query(self, query_info: Dict, full_content: str) -> Dict:
        """Analyze a single query for vulnerabilities"""
        query_text = query_info['text']
        line_num = query_info['line']
        
        analysis = {
            'query': query_text[:100] + '...' if len(query_text) > 100 else query_text,
            'line': line_num,
            'is_vulnerable': False,
            'has_warnings': False,
            'issues': [],
            'security_level': 'safe'
        }
        
        # Check for string formatting vulnerabilities
        if self._has_string_formatting(query_text):
            analysis['is_vulnerable'] = True
            analysis['security_level'] = 'vulnerable'
            analysis['issues'].append('Uses string formatting which can lead to SQL injection')
        
        # Check for f-string usage
        if query_text.startswith('f"') or query_text.startswith("f'"):
            analysis['has_warnings'] = True
            analysis['security_level'] = 'warning'
            analysis['issues'].append('Uses f-string - ensure no user input is interpolated')
        
        # Check for proper parameterization
        if '%s' in query_text and not self._has_string_formatting(query_text):
            analysis['security_level'] = 'safe'
            analysis['issues'].append('Uses proper parameterization with %s placeholders')
        
        # Check for dynamic query building
        if 'format(' in query_text or '.format' in query_text:
            analysis['is_vulnerable'] = True
            analysis['security_level'] = 'vulnerable'
            analysis['issues'].append('Uses .format() method which can be vulnerable')
        
        # Check for concatenation
        if '+' in query_text and ('SELECT' in query_text.upper() or 'WHERE' in query_text.upper()):
            analysis['has_warnings'] = True
            analysis['security_level'] = 'warning'
            analysis['issues'].append('Possible string concatenation in SQL query')
        
        return analysis
    
    def _has_string_formatting(self, query: str) -> bool:
        """Check if query uses dangerous string formatting"""
        dangerous_patterns = [
            r'%\s*\(',  # % formatting
            r'\.format\s*\(',  # .format() method
            r'\{[^}]*\}',  # format placeholders without proper escaping
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, query):
                return True
        return False
    
    def generate_report(self, results: List[Dict]) -> str:
        """Generate a comprehensive security report"""
        report = []
        report.append("=" * 80)
        report.append("SQL INJECTION SECURITY ANALYSIS REPORT")
        report.append("=" * 80)
        report.append("")
        
        total_files = len(results)
        total_queries = sum(r.get('total_queries', 0) for r in results)
        total_vulnerabilities = sum(len(r.get('vulnerabilities', [])) for r in results)
        total_warnings = sum(len(r.get('warnings', [])) for r in results)
        total_safe = sum(len(r.get('safe_queries', [])) for r in results)
        
        report.append(f"SUMMARY:")
        report.append(f"  Files analyzed: {total_files}")
        report.append(f"  Total queries: {total_queries}")
        report.append(f"  Vulnerabilities: {total_vulnerabilities}")
        report.append(f"  Warnings: {total_warnings}")
        report.append(f"  Safe queries: {total_safe}")
        report.append("")
        
        for result in results:
            if result.get('error'):
                report.append(f"ERROR in {result['file']}: {result['error']}")
                continue
                
            report.append(f"FILE: {result['file']}")
            report.append("-" * 60)
            
            if result['vulnerabilities']:
                report.append("🚨 VULNERABILITIES:")
                for vuln in result['vulnerabilities']:
                    report.append(f"  Line {vuln['line']}: {vuln['security_level'].upper()}")
                    report.append(f"    Query: {vuln['query']}")
                    for issue in vuln['issues']:
                        report.append(f"    Issue: {issue}")
                    report.append("")
            
            if result['warnings']:
                report.append("⚠️  WARNINGS:")
                for warn in result['warnings']:
                    report.append(f"  Line {warn['line']}: {warn['security_level'].upper()}")
                    report.append(f"    Query: {warn['query']}")
                    for issue in warn['issues']:
                        report.append(f"    Issue: {issue}")
                    report.append("")
            
            if result['safe_queries']:
                report.append("✅ SAFE QUERIES:")
                for safe in result['safe_queries']:
                    report.append(f"  Line {safe['line']}: Properly parameterized")
                report.append("")
            
            report.append("")
        
        # Security recommendations
        report.append("SECURITY RECOMMENDATIONS:")
        report.append("=" * 40)
        report.append("1. Always use parameterized queries with %s placeholders")
        report.append("2. Never use string formatting (.format(), %, f-strings) with user input")
        report.append("3. Validate and sanitize all user inputs before database operations")
        report.append("4. Use whitelist validation for dynamic table/column names")
        report.append("5. Implement proper error handling that doesn't leak sensitive information")
        report.append("")
        
        return "\n".join(report)

def main():
    """Main analysis function"""
    analyzer = SQLSecurityAnalyzer()
    
    # Files to analyze
    files_to_analyze = [
        'backend/src/bnb_routes.py',
        'backend/src/str_channel_routes.py',
        'backend/src/str_invoice_routes.py'
    ]
    
    results = []
    
    for filepath in files_to_analyze:
        if os.path.exists(filepath):
            print(f"Analyzing {filepath}...")
            result = analyzer.analyze_file(filepath)
            results.append(result)
        else:
            print(f"Warning: {filepath} not found")
            results.append({
                'file': filepath,
                'error': 'File not found',
                'vulnerabilities': [],
                'warnings': [],
                'safe_queries': [],
                'total_queries': 0
            })
    
    # Generate and save report
    report = analyzer.generate_report(results)
    
    # Save to file
    with open('backend/sql_security_report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    
    print("\n" + report)
    
    # Return summary for programmatic use
    total_vulnerabilities = sum(len(r.get('vulnerabilities', [])) for r in results)
    total_warnings = sum(len(r.get('warnings', [])) for r in results)
    
    return {
        'total_vulnerabilities': total_vulnerabilities,
        'total_warnings': total_warnings,
        'results': results,
        'report_file': 'backend/sql_security_report.txt'
    }

if __name__ == '__main__':
    main()