#!/usr/bin/env python
"""Python 代码质量分析器

支持功能：
- 代码规范检查 (flake8)
- 代码质量分析 (pylint)
- 安全漏洞扫描 (bandit)
- 代码复杂度分析 (radon)
"""

import subprocess
import json
import os
import sys
from pathlib import Path
from datetime import datetime


class CodeAnalyzer:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.results = {
            'project': str(project_path),
            'timestamp': datetime.now().isoformat(),
            'issues': [],
            'summary': {}
        }
    
    def check_flake8(self) -> dict:
        """使用 flake8 检查代码规范"""
        print('📋 运行 flake8 代码规范检查...')
        try:
            result = subprocess.run(
                ['flake8', str(self.project_path), '--max-line-length=100', '--format=json'],
                capture_output=True,
                text=True
            )
            issues = []
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        try:
                            issue = json.loads(line)
                            issues.append({
                                'type': 'style',
                                'severity': 'warning',
                                'file': issue.get('filename', ''),
                                'line': issue.get('line_number', 0),
                                'column': issue.get('column_number', 0),
                                'code': issue.get('code', ''),
                                'message': issue.get('text', '')
                            })
                        except json.JSONDecodeError:
                            continue
            return {'tool': 'flake8', 'issues': issues, 'count': len(issues)}
        except FileNotFoundError:
            return {'tool': 'flake8', 'error': 'flake8 未安装，请运行：pip install flake8', 'issues': []}
        except Exception as e:
            return {'tool': 'flake8', 'error': str(e), 'issues': []}
    
    def check_pylint(self) -> dict:
        """使用 pylint 进行代码质量分析"""
        print('📊 运行 pylint 代码质量分析...')
        try:
            result = subprocess.run(
                ['pylint', str(self.project_path), '--output-format=json'],
                capture_output=True,
                text=True
            )
            issues = []
            if result.stdout:
                try:
                    pylint_data = json.loads(result.stdout)
                    for msg in pylint_data:
                        severity = 'error' if msg.get('type') in ['error', 'fatal'] else 'warning'
                        issues.append({
                            'type': 'quality',
                            'severity': severity,
                            'file': msg.get('path', ''),
                            'line': msg.get('line', 0),
                            'column': msg.get('column', 0),
                            'code': msg.get('symbol', ''),
                            'message': msg.get('message', '')
                        })
                except json.JSONDecodeError:
                    pass
            return {'tool': 'pylint', 'issues': issues, 'count': len(issues)}
        except FileNotFoundError:
            return {'tool': 'pylint', 'error': 'pylint 未安装，请运行：pip install pylint', 'issues': []}
        except Exception as e:
            return {'tool': 'pylint', 'error': str(e), 'issues': []}
    
    def check_bandit(self) -> dict:
        """使用 bandit 进行安全漏洞扫描"""
        print('🔒 运行 bandit 安全漏洞扫描...')
        try:
            result = subprocess.run(
                ['bandit', '-r', str(self.project_path), '-f', 'json'],
                capture_output=True,
                text=True
            )
            issues = []
            if result.stdout:
                try:
                    bandit_data = json.loads(result.stdout)
                    for issue in bandit_data.get('results', []):
                        issues.append({
                            'type': 'security',
                            'severity': issue.get('issue_severity', 'medium').lower(),
                            'file': issue.get('filename', ''),
                            'line': issue.get('line_number', 0),
                            'code': issue.get('test_id', ''),
                            'message': issue.get('issue_text', '')
                        })
                except json.JSONDecodeError:
                    pass
            return {'tool': 'bandit', 'issues': issues, 'count': len(issues)}
        except FileNotFoundError:
            return {'tool': 'bandit', 'error': 'bandit 未安装，请运行：pip install bandit', 'issues': []}
        except Exception as e:
            return {'tool': 'bandit', 'error': str(e), 'issues': []}
    
    def check_radon(self) -> dict:
        """使用 radon 进行代码复杂度分析"""
        print('📈 运行 radon 代码复杂度分析...')
        try:
            result = subprocess.run(
                ['radon', 'cc', str(self.project_path), '-a', '-s', '-j'],
                capture_output=True,
                text=True
            )
            issues = []
            if result.stdout:
                try:
                    radon_data = json.loads(result.stdout)
                    for file_path, blocks in radon_data.items():
                        for block in blocks:
                            if block.get('complexity', 0) > 10:
                                issues.append({
                                    'type': 'complexity',
                                    'severity': 'warning' if block['complexity'] <= 20 else 'error',
                                    'file': file_path,
                                    'line': block.get('line', 0),
                                    'code': f"C{block.get('complexity', 0)}",
                                    'message': f"函数 '{block.get('name', '')}' 复杂度过高：{block.get('complexity', 0)}"
                                })
                except json.JSONDecodeError:
                    pass
            return {'tool': 'radon', 'issues': issues, 'count': len(issues)}
        except FileNotFoundError:
            return {'tool': 'radon', 'error': 'radon 未安装，请运行：pip install radon', 'issues': []}
        except Exception as e:
            return {'tool': 'radon', 'error': str(e), 'issues': []}
    
    def analyze(self, checks: list = None) -> dict:
        """执行综合分析"""
        if checks is None:
            checks = ['flake8', 'pylint', 'bandit', 'radon']
        
        print(f'🚀 开始分析项目：{self.project_path}')
        print('=' * 50)
        
        all_issues = []
        
        if 'flake8' in checks:
            result = self.check_flake8()
            all_issues.extend(result.get('issues', []))
            if 'error' in result:
                print(f"  ⚠️  {result['error']}")
            else:
                print(f"  ✅ 发现 {result['count']} 个规范问题")
        
        if 'pylint' in checks:
            result = self.check_pylint()
            all_issues.extend(result.get('issues', []))
            if 'error' in result:
                print(f"  ⚠️  {result['error']}")
            else:
                print(f"  ✅ 发现 {result['count']} 个质量问题")
        
        if 'bandit' in checks:
            result = self.check_bandit()
            all_issues.extend(result.get('issues', []))
            if 'error' in result:
                print(f"  ⚠️  {result['error']}")
            else:
                print(f"  ✅ 发现 {result['count']} 个安全问题")
        
        if 'radon' in checks:
            result = self.check_radon()
            all_issues.extend(result.get('issues', []))
            if 'error' in result:
                print(f"  ⚠️  {result['error']}")
            else:
                print(f"  ✅ 发现 {result['count']} 个复杂度问题")
        
        print('=' * 50)
        
        # 统计摘要
        summary = {
            'total': len(all_issues),
            'by_severity': {},
            'by_type': {}
        }
        for issue in all_issues:
            sev = issue.get('severity', 'unknown')
            typ = issue.get('type', 'unknown')
            summary['by_severity'][sev] = summary['by_severity'].get(sev, 0) + 1
            summary['by_type'][typ] = summary['by_type'].get(typ, 0) + 1
        
        self.results['issues'] = all_issues
        self.results['summary'] = summary
        
        return self.results
    
    def print_report(self):
        """打印格式化的检测报告"""
        print('\n' + '=' * 60)
        print('📊 代码分析报告')
        print('=' * 60)
        print(f"项目：{self.results['project']}")
        print(f"时间：{self.results['timestamp']}")
        print(f"总问题数：{self.results['summary'].get('total', 0)}")
        
        print('\n按严重程度分布:')
        for sev, count in self.results['summary'].get('by_severity', {}).items():
            print(f"  {sev}: {count}")
        
        print('\n按类型分布:')
        for typ, count in self.results['summary'].get('by_type', {}).items():
            print(f"  {typ}: {count}")
        
        print('\n详细问题列表:')
        print('-' * 60)
        for i, issue in enumerate(self.results['issues'][:50], 1):  # 限制显示前 50 个
            print(f"{i}. [{issue['severity'].upper()}] {issue['message']}")
            print(f"   文件：{issue['file']}:{issue['line']}")
            print()
        
        if len(self.results['issues']) > 50:
            print(f"... 还有 {len(self.results['issues']) - 50} 个问题未显示")
        
        print('=' * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Python 代码质量分析器')
    parser.add_argument('project_path', help='要分析的项目路径')
    parser.add_argument('--checks', nargs='+', choices=['flake8', 'pylint', 'bandit', 'radon'],
                       default=['flake8', 'pylint', 'bandit', 'radon'],
                       help='选择要运行的检查类型')
    parser.add_argument('--output', '-o', help='输出报告文件路径')
    
    args = parser.parse_args()
    
    analyzer = CodeAnalyzer(args.project_path)
    results = analyzer.analyze(args.checks)
    analyzer.print_report()
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n✅ 报告已保存到：{args.output}")


if __name__ == '__main__':
    main()
