#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import json

def test_data_save():
    """テストデータをデータベースに保存"""
    
    # テストデータ
    test_data = [
        {
            "ページ": "1",
            "出荷日": "2025-01-15",
            "受注番号": "ORD-001",
            "納入先番号": "DEL-001",
            "担当者": "田中太郎",
            "税抜合計": "15000"
        },
        {
            "ページ": "2",
            "出荷日": "2025-01-16",
            "受注番号": "ORD-002",
            "納入先番号": "DEL-002",
            "担当者": "佐藤花子",
            "税抜合計": "25000"
        }
    ]
    
    try:
        # データベースに接続
        conn = sqlite3.connect('inventory_data.db')
        cursor = conn.cursor()
        
        # 既存データをクリア
        cursor.execute('DELETE FROM basic_info')
        
        # テストデータを挿入
        for item in test_data:
            cursor.execute('''
                INSERT INTO basic_info (ページ, 出荷日, 受注番号, 納入先番号, 担当者, 税抜合計)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                item['ページ'],
                item['出荷日'],
                item['受注番号'],
                item['納入先番号'],
                item['担当者'],
                item['税抜合計']
            ))
        
        conn.commit()
        print(f"テストデータ {len(test_data)} 件を保存しました")
        
        # 保存されたデータを確認
        cursor.execute('SELECT * FROM basic_info')
        rows = cursor.fetchall()
        print(f"データベース内のレコード数: {len(rows)}")
        
        for row in rows:
            print(f"ID: {row[0]}, ページ: {row[1]}, 出荷日: {row[2]}, 受注番号: {row[3]}, 納入先番号: {row[4]}, 担当者: {row[5]}, 税抜合計: {row[6]}")
        
        conn.close()
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    test_data_save()
