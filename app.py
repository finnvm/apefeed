import sqlite3
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from pytubefix import Channel
import random
import time
from datetime import datetime
import pytz

app = Flask(__name__)
app.secret_key = 'some_secret_key'  # For flash messages

DATABASE = 'apefeed.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Fetch videos in background thread
def fetch_videos_in_batches(channel_url, tags, channel_name, batch_size=10):
    try:
        channel = Channel(channel_url)
        conn = get_db_connection()
        cursor = conn.cursor()

        for i, video in enumerate(channel.videos):
            # Insert video data in batches
            cursor.execute(
                'INSERT OR IGNORE INTO videos (title, url, publish_date, tags, channel_name, channel_url) VALUES (?, ?, ?, ?, ?, ?)',
                (video.title, video.watch_url, video.publish_date, tags, channel_name, channel_url)
            )

            # Commit every `batch_size` videos
            if (i + 1) % batch_size == 0:
                conn.commit()
                time.sleep(1)  # Small delay to avoid bot detection

        conn.commit()  # Final commit for any remaining videos
        conn.close()
    except Exception as e:
        print(f"Error fetching videos: {e}")

@app.route('/')
def home():
    return redirect(url_for('ape_feed'))

@app.route('/feed-the-ape', methods=['GET', 'POST'])
def feed_the_ape():
    if request.method == 'POST':
        youtube_url = request.form['youtube_url']
        youtube_channel_name = request.form['youtube_channel_name']
        tags = request.form['tags']
        tags = ', '.join([tag.strip() for tag in tags.split(',')])

        # Run video fetching in a separate thread
        fetch_thread = threading.Thread(target=fetch_videos_in_batches, args=(youtube_url, tags, youtube_channel_name))
        fetch_thread.start()

        # Redirect to loading screen or feed page
        flash("Channel is being added. Videos will appear in the feed shortly.")
        return redirect(url_for('ape_feed'))

    return render_template('feed_the_ape.html')

@app.route('/ape-feed', methods=['GET'])
def ape_feed():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Pagination parameters (only relevant if not sorting by random)
    page = int(request.args.get('page', 1))
    items_per_page = 10
    offset = (page - 1) * items_per_page

    # Filter and sort options
    tags_filter = request.args.getlist('tags')
    channel_filter = request.args.getlist('channel_filter')
    print(channel_filter)
    #sort_order = request.args.get('sort', 'publish_date DESC')
    sort_order = request.args.get('sort') or 'publish_date DESC'


    # Handle random sorting separately
    if sort_order == "RANDOM()":
        if tags_filter:
            query = f'''
                SELECT * FROM videos 
                WHERE tags LIKE "%" || ? || "%" 
                ORDER BY RANDOM() 
                LIMIT ?
            '''
            videos = cursor.execute(query, tags_filter + [items_per_page]).fetchall()
        else:
            query = 'SELECT * FROM videos ORDER BY RANDOM() LIMIT ?'
            videos = cursor.execute(query, (items_per_page,)).fetchall()
        
        # Close connection and render template with shuffle option
        conn.close()
        return render_template('ape_feed.html', videos=videos, random_sort=True)
    
    # Standard sorting and pagination
    if tags_filter and tags_filter[0] != '':
        print('tags_filter')
        tags_placeholder = ','.join(['?'] * len(tags_filter))
        query = f'''
            SELECT * FROM videos 
            WHERE tags LIKE "%" || ? || "%" 
            ORDER BY {sort_order} 
            LIMIT ? OFFSET ?
        '''
        videos = cursor.execute(query, tags_filter + [items_per_page, offset]).fetchall()
        #print(len(videos))

        total_items_query = f'''
            SELECT * FROM videos 
            WHERE tags LIKE "%" 
        '''

        total_items_query = cursor.execute(f'SELECT COUNT(*) FROM videos where tags like "%{tags_filter[0]}%"').fetchone()
    elif channel_filter:
        print('channel_filter')
        channels_placeholder = ','.join(['?'] * len(channel_filter))
        query = f'''
            SELECT * FROM videos 
            WHERE channel_name LIKE "%" || ? || "%" 
            ORDER BY {sort_order} 
            LIMIT ? OFFSET ?
        '''
        videos = cursor.execute(query, channel_filter + [items_per_page, offset]).fetchall()
        #print(len(videos))

        total_items_query = f'''
            SELECT * FROM videos 
            WHERE channel_name LIKE "%" 
        '''

        total_items_query = cursor.execute(f'SELECT COUNT(*) FROM videos where channel_name like "%{channel_filter[0]}%"').fetchone()
    else:
        query = f'SELECT * FROM videos ORDER BY {sort_order} LIMIT ? OFFSET ?'
        videos = cursor.execute(query, (items_per_page, offset)).fetchall()



        # Get the total number of items for pagination calculation
        total_items_query = cursor.execute('SELECT COUNT(*) FROM videos').fetchone()
    total_items = total_items_query[0] if total_items_query else 0
    total_pages = (total_items + items_per_page - 1) // items_per_page  # Round up

    conn.close()
    return render_template('ape_feed.html', videos=videos, page=page, total_pages=total_pages, random_sort=False, sort_order=sort_order)




@app.route('/video/<int:video_id>')
def view_video(video_id):
    conn = get_db_connection()
    video = conn.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()
    conn.close()
    if video is None:
        return "Video not found.", 404
    return redirect(video['url'])

@app.route('/api/feed', methods=['GET'])
def api_feed():
    conn = get_db_connection()
    cursor = conn.cursor()

    tags_filter = request.args.getlist('tags')
    #sort_order = request.args.get('sort', 'publish_date DESC')
    sort_order = request.args.get('sort') or 'publish_date DESC'


    if tags_filter:
        tags_placeholder = ','.join(['?'] * len(tags_filter))
        query = f'SELECT * FROM videos WHERE tags LIKE "%" || ? || "%" ORDER BY {sort_order}'
        videos = cursor.execute(query, tags_filter).fetchall()
    else:
        videos = cursor.execute(f'SELECT * FROM videos ORDER BY {sort_order}').fetchall()

    videos = [dict(video) for video in videos]
    conn.close()
    return jsonify(videos)


@app.template_filter('format_datetime')
def format_datetime(value, format="%B %d, %Y, %I:%M %p", target_timezone="UTC"):
    try:
        # Parse the datetime string with timezone info
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S%z")
        
        # Convert to the target timezone
        target_tz = pytz.timezone(target_timezone)
        dt = dt.astimezone(target_tz)
        
        # Format the datetime
        return dt.strftime(format)
    except ValueError:
        return value  # Return as-is if there's an error










def insert_video(video):
    print('insert video?')
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Prepare SQL to insert data into videos table
    sql = '''
    INSERT INTO videos (title, url, publish_date, channel_name, channel_url)
    VALUES (?, ?, ?, ?, ?)
    '''
    cursor.execute(sql, (video['title'], video['url'], video['publish_date'], video['channel_name'], video['channel_url']))
    conn.commit()
    conn.close()

@app.route('/add_video', methods=['POST'])
def add_video():
    print('add video?')
    video = request.json

    try:
        # Insert video into the database
        insert_video(video)
        return jsonify({"status": "success"}), 201
    except Exception as e:
        print("Error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500








if __name__ == '__main__':
    app.run(debug=True)
