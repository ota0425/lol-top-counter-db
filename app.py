import json
import html
import sqlite3

import streamlit as st

from icons import icon_markup

from db import (connect, VIDEO_URL, CATEGORIES, seconds, timestamp, video_link,
                parse_captions, import_chapters, validate_source, restore_backup,
                install_dataset, matches_champion, search_tips, search_key)

st.set_page_config(page_title='LoL 対面対策DB', page_icon='🛡️', layout='wide')
conn = connect()
install_dataset(conn)
st.title('🛡️ LoL 対面対策DB')
st.caption('チャンピオン名からTOP・MIDの対策を検索')
checklist_count = sum(len(json.loads(row[0])) for row in conn.execute('SELECT checklist_json FROM champions'))
col1, col2 = st.columns(2)
col1.metric('収録チャンピオン', conn.execute('SELECT COUNT(*) FROM champions').fetchone()[0])
col2.metric('対策チェックポイント', checklist_count)
search_tab, review_tab, setup_tab = st.tabs(['🔎 対策を検索', '✍️ 対策を登録・確認', '⚙️ 字幕・チャプターを取り込む'])

with setup_tab:
    st.subheader('1. チャプターを登録')
    st.write('概要欄のチャプターを「時刻 チャンピオン名」の形式で貼り付けます。動画の概要欄にある時刻を使用してください。')
    chapters_text = st.text_area('チャプター一覧', placeholder='0:00 チャンピオン名\n15:44 次のチャンピオン名', height=180)
    if st.button('チャプターを登録', type='primary'):
        try:
            count = import_chapters(conn, chapters_text)
            st.success(f'{count}件のチャプターを登録しました。')
        except ValueError as e:
            st.error(str(e))
    st.divider()
    st.subheader('2. 字幕を取り込む（任意）')
    st.write('動画の字幕を `.srt` または `.vtt` 形式で用意してアップロードしてください。字幕がなくても対策の手入力は可能です。')
    source_options = [dict(r) for r in conn.execute('SELECT video_url,MIN(name) AS label FROM champions GROUP BY video_url ORDER BY MIN(id)')]
    selected_source = st.selectbox('字幕の対象動画', source_options, format_func=lambda v: '最初のTOPまとめ動画' if v['video_url']==VIDEO_URL else v['label']+'の対策動画')
    uploaded = st.file_uploader('字幕ファイル', type=['srt', 'vtt'])
    if uploaded is not None and st.button('字幕を取り込む'):
        try:
            content = uploaded.getvalue().decode('utf-8-sig')
            rows = parse_captions(content)
            if not rows:
                st.warning('字幕行が見つかりません。SRT/VTTの形式を確認してください。')
            else:
                conn.executemany('INSERT OR IGNORE INTO transcript(start_sec,end_sec,content,video_url) VALUES(?,?,?,?)', [(*r, selected_source['video_url']) for r in rows])
                conn.commit()
                st.success(f'{len(rows)}行を読み込みました。')
        except UnicodeDecodeError:
            st.error('UTF-8形式の字幕ファイルを使用してください。')
    st.caption('字幕を追加すると、管理画面で該当区間の内容を確認できます。')

with setup_tab:
    st.divider()
    st.subheader('3. バックアップJSONから復元')
    st.caption('既存のデータに追加します。同じ内容の対策は重複登録しません。')
    backup = st.file_uploader('バックアップJSON', type=['json'])
    if backup is not None and st.button('JSONを取り込む'):
        try:
            count = restore_backup(conn, json.loads(backup.getvalue().decode('utf-8-sig')))
            st.success(f'{count}件の対策を追加しました。')
        except (ValueError, TypeError, sqlite3.Error) as e:
            st.error(f'取り込めませんでした: {e}')

champions = [dict(row) for row in conn.execute('SELECT * FROM champions ORDER BY id')]

with search_tab:
    if not champions:
        st.info('まず「字幕・チャプターを取り込む」でチャンピオンを登録してください。')
    else:
        keyword = st.text_input('対面チャンピオン名で検索', placeholder='例：カミール / かみーる / Camille')
        matches = [c for c in champions if matches_champion(keyword, c['name'])]
        exact_matches = [c for c in matches if search_key(c['name']) == search_key(keyword)]
        if exact_matches:
            matches = exact_matches
        st.caption(f'{len(matches)}チャンピオンが一致')
        if not matches:
            st.warning('一致するチャンピオンがありません。')
        for champ in matches:
            with st.expander(champ['name'], expanded=len(matches)==1):
                checklist = json.loads(champ['checklist_json'])
                for i, item in enumerate(checklist, 1):
                    st.html(f'<div style="font-weight:650;padding:9px 0;line-height:1.9">{i}. {icon_markup(item, champ["name"], True)}</div>')
                supplements = json.loads(champ['supplements_json'])
                if supplements:
                    st.markdown('**追加の対策**')
                    for item in supplements:
                        st.html(f"<p>・{icon_markup(item['detail'], champ['name'])}</p>")
                tips = search_tips(conn, champ['id'])
                if not tips:
                    st.info('対策はまだ登録されていません。')
                if tips:
                    with st.popover('詳しい立ち回り・補足'):
                        for tip in tips:
                            st.html(f"<p><strong>{html.escape(tip['category'])}</strong> — {icon_markup(tip['detail'], champ['name'])}</p>")

with review_tab:
    if not champions:
        st.info('先にチャプターを登録してください。')
    else:
        selected = st.selectbox('チャンピオン', champions, format_func=lambda c: c['name'])
        st.markdown(f"[動画の該当位置を開く]({video_link(selected['start_sec'], selected['video_url'])})")
        start, end = selected['start_sec'], selected['end_sec']
        if end is None:
            transcript_rows = conn.execute('SELECT * FROM transcript WHERE video_url=? AND start_sec>=? ORDER BY start_sec', (selected['video_url'],start)).fetchall()
        else:
            transcript_rows = conn.execute('SELECT * FROM transcript WHERE video_url=? AND start_sec>=? AND start_sec<? ORDER BY start_sec', (selected['video_url'],start,end)).fetchall()
        st.subheader('文字起こし（確認用）')
        if transcript_rows:
            full_text = '\n'.join(f"[{timestamp(r['start_sec'])}] {r['content']}" for r in transcript_rows)
            st.text_area('字幕', value=full_text, height=230)
        else:
            st.info('この区間の字幕は未登録です。動画を見ながら手動で登録できます。')
        st.subheader('対策を追加')
        with st.form('add_tip', clear_on_submit=True):
            category = st.selectbox('分類', CATEGORIES)
            detail = st.text_area('対策内容（動画で実際に説明された内容）')
            source = st.text_input('根拠の時刻（例：1:15:30）', value=timestamp(start))
            status = st.radio('確認状況', ['未確認', '確認済み'], horizontal=True)
            submitted = st.form_submit_button('保存')
            if submitted:
                try:
                    if not detail.strip():
                        raise ValueError('対策内容を入力してください。')
                    sec = seconds(source) if source.strip() else None
                    if status == '確認済み':
                        validate_source(sec, selected)
                    conn.execute('INSERT INTO tips(champion_id,category,detail,source_sec,status) VALUES(?,?,?,?,?)', (selected['id'],category,detail.strip(),sec,status))
                    conn.commit()
                    st.success('保存しました。')
                except ValueError as e:
                    st.error(str(e))
        st.subheader('登録済みの対策')
        existing = conn.execute('SELECT * FROM tips WHERE champion_id=? ORDER BY id', (selected['id'],)).fetchall()
        for tip in existing:
            with st.expander(f"#{tip['id']} [{tip['status']}] {tip['category']} — {tip['detail'][:45]}"):
                st.write(tip['detail'])
                if tip['source_sec'] is not None:
                    st.markdown(f"[動画で確認]({video_link(tip['source_sec'], selected['video_url'])})")
                with st.form(f"edit_{tip['id']}"):
                    edit_category = st.selectbox('分類', CATEGORIES, index=CATEGORIES.index(tip['category']))
                    edit_detail = st.text_area('対策内容', value=tip['detail'])
                    edit_source = st.text_input('根拠の時刻', value=timestamp(tip['source_sec']) if tip['source_sec'] is not None else '')
                    edit_status = st.selectbox('確認状況', ['未確認', '確認済み'], index=int(tip['status']=='確認済み'))
                    if st.form_submit_button('変更を保存'):
                        try:
                            if not edit_detail.strip():
                                raise ValueError('対策内容を入力してください。')
                            sec = seconds(edit_source) if edit_source.strip() else None
                            if edit_status == '確認済み' or tip['origin']=='subtitle_summary':
                                validate_source(sec, selected)
                            conn.execute('UPDATE tips SET category=?,detail=?,source_sec=?,status=? WHERE id=?',
                                         (edit_category,edit_detail.strip(),sec,edit_status,tip['id']))
                            conn.commit()
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
                c1,c2 = st.columns(2)
                if c1.button('確認済みにする', key=f"approve_{tip['id']}", disabled=tip['status']=='確認済み'):
                    try:
                        validate_source(tip['source_sec'], selected)
                        conn.execute('UPDATE tips SET status=? WHERE id=?', ('確認済み',tip['id']))
                        conn.commit()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                if c2.button('削除', key=f"delete_{tip['id']}"):
                    conn.execute('DELETE FROM tips WHERE id=?', (tip['id'],))
                    conn.commit()
                    st.rerun()
        st.divider()
        st.subheader('バックアップ')
        export_data = {'video_url':VIDEO_URL, 'champions':[]}
        for champ in champions:
            item = dict(champ)
            item['checklist'] = json.loads(item.pop('checklist_json'))
            item['supplements'] = json.loads(item.pop('supplements_json'))
            item['tips'] = [dict(r) for r in conn.execute('SELECT * FROM tips WHERE champion_id=? ORDER BY id', (champ['id'],))]
            export_data['champions'].append(item)
        st.download_button('JSON形式でエクスポート', json.dumps(export_data, ensure_ascii=False, indent=2), file_name='lol_top_counters.json', mime='application/json')
