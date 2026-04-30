#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询 Neo4j 数据库中的所有节点和关系"""

import os
from neo4j import GraphDatabase

# Neo4j 连接配置
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'neo4j_pass')

def query_neo4j():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        print("=" * 60)
        print("🔍 Neo4j 数据库查询结果")
        print("=" * 60)
        
        # 1. 查询所有节点
        print("\n📦 所有节点:")
        print("-" * 40)
        result = session.run("MATCH (n) RETURN n ORDER BY n.name")
        nodes = [record["n"] for record in result]
        
        if not nodes:
            print("  (没有找到任何节点)")
        else:
            for node in nodes:
                props = dict(node)
                print(f"  ✅ {props.get('name', 'N/A')}")
                print(f"     - UUID: {props.get('uuid', 'N/A')[:20]}...")
                print(f"     - Type: {props.get('entity_type', 'N/A')}")
                print(f"     - Group: {props.get('group_id', 'N/A')[:30]}..." if props.get('group_id') else "     - Group: (空)")
                print(f"     - Summary: {props.get('summary', 'N/A')[:50]}..." if props.get('summary') else "     - Summary: (空)")
                print()
        
        # 2. 按 group_id 分组统计
        print("\n📊 按 Group 分组统计:")
        print("-" * 40)
        result = session.run("""
            MATCH (n) 
            WHERE n.group_id IS NOT NULL AND n.group_id <> ''
            RETURN n.group_id as group_id, count(*) as count
        """)
        groups = list(result)
        
        if not groups:
            print("  (没有找到分组)")
        else:
            for record in groups:
                print(f"  📁 {record['group_id']}: {record['count']} 个节点")
        
        # 3. 查询所有关系
        print("\n🔗 所有关系:")
        print("-" * 40)
        result = session.run("""
            MATCH (a)-[r]->(b) 
            RETURN a.name as from, type(r) as relation, b.name as to
        """)
        relations = list(result)
        
        if not relations:
            print("  (没有找到任何关系)")
        else:
            for rel in relations:
                print(f"  {rel['from']} --[{rel['relation']}]--> {rel['to']}")
        
        # 4. 展点详情（group_id = '展点'）
        print("\n🏷️ '展点' 分组详情:")
        print("-" * 40)
        result = session.run("""
            MATCH (n) 
            WHERE n.group_id = '展点'
            RETURN n.name as name, n.summary as summary, n.entity_type as type
        """)
        exhibits = list(result)
        
        if not exhibits:
            print("  (没有找到展点)")
        else:
            for i, record in enumerate(exhibits, 1):
                print(f"  {i}. {record['name']}")
                if record['summary']:
                    print(f"     摘要: {record['summary'][:80]}...")
                print()
        
        # 5. 总计
        print("\n📈 统计信息:")
        print("-" * 40)
        result = session.run("""
            MATCH (n) 
            RETURN count(n) as total_nodes
        """)
        stats = list(result)[0]
        print(f"  总节点数: {stats['total_nodes']}")
        
    driver.close()
    print("\n" + "=" * 60)
    print("✅ 查询完成")
    print("=" * 60)

if __name__ == "__main__":
    try:
        query_neo4j()
    except Exception as e:
        print(f"\n❌ 查询失败: {e}")
        print("\n请确保:")
        print("  1. Neo4j 服务正在运行")
        print("  2. 环境变量 NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD 设置正确")
