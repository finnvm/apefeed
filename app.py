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
def fetch_videos_in_batches(channel_url, tags, batch_size=10):
    try:
        channel = Channel(channel_url)
        conn = get_db_connection()
        cursor = conn.cursor()

        for i, video in enumerate(channel.videos):
            # Insert video data in batches
            cursor.execute(
                'INSERT OR IGNORE INTO videos (title, url, publish_date, tags) VALUES (?, ?, ?, ?)',
                (video.title, video.watch_url, video.publish_date, tags)
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
        tags = request.form['tags']
        tags = ', '.join([tag.strip() for tag in tags.split(',')])

        # Run video fetching in a separate thread
        fetch_thread = threading.Thread(target=fetch_videos_in_batches, args=(youtube_url, tags))
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
    sort_order = request.args.get('sort', 'publish_date')

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
    if tags_filter:
        tags_placeholder = ','.join(['?'] * len(tags_filter))
        query = f'''
            SELECT * FROM videos 
            WHERE tags LIKE "%" || ? || "%" 
            ORDER BY {sort_order} desc 
            LIMIT ? OFFSET ?
        '''
        videos = cursor.execute(query, tags_filter + [items_per_page, offset]).fetchall()
    else:
        query = f'SELECT * FROM videos ORDER BY {sort_order} desc LIMIT ? OFFSET ?'
        videos = cursor.execute(query, (items_per_page, offset)).fetchall()

    # Get the total number of items for pagination calculation
    total_items_query = cursor.execute('SELECT COUNT(*) FROM videos').fetchone()
    total_items = total_items_query[0] if total_items_query else 0
    total_pages = (total_items + items_per_page - 1) // items_per_page  # Round up

    conn.close()
    return render_template('ape_feed.html', videos=videos, page=page, total_pages=total_pages, random_sort=False)




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
    sort_order = request.args.get('sort', 'publish_date')

    if tags_filter:
        tags_placeholder = ','.join(['?'] * len(tags_filter))
        query = f'SELECT * FROM videos WHERE tags LIKE "%" || ? || "%" ORDER BY {sort_order} desc'
        videos = cursor.execute(query, tags_filter).fetchall()
    else:
        videos = cursor.execute(f'SELECT * FROM videos ORDER BY {sort_order} desc').fetchall()

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


if __name__ == '__main__':
    app.run(debug=True)
