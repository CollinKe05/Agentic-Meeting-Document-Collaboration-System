# backend/app.py
from flask import Flask, jsonify, request, send_from_directory
import os
# Import database functions later
from database import init_db, add_task, get_tasks, update_task, delete_task # Corrected import

app = Flask(__name__, static_folder='../frontend', static_url_path='')

# Placeholder for database path
DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'tasks.db')

# Serve the main HTML file
@app.route('/')
def index():
    # Ensure the frontend directory and index.html exist
    frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend')
    if not os.path.exists(os.path.join(frontend_dir, 'index.html')):
         return "Frontend not found!", 404
    return send_from_directory(frontend_dir, 'index.html')


# --- API Endpoints ---

# Get all tasks
@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    tasks = get_tasks(DATABASE_PATH) # Use the actual function
    return jsonify(tasks)

# Add a new task
@app.route('/api/tasks', methods=['POST'])
def api_add_task():
    data = request.json
    if not data or 'title' not in data or not data['title']:
         return jsonify({"message": "Task title is required"}), 400
    try:
        task_id = add_task(DATABASE_PATH, data)
        if task_id:
             # Fetch the newly added task to return it
             # This requires a get_task_by_id function in database.py (implement later if needed)
             # For now, just return success
             return jsonify({"message": "Task added successfully", "id": task_id}), 201
        else:
             return jsonify({"message": "Failed to add task"}), 500
    except Exception as e:
        print(f"Error adding task: {e}")
        return jsonify({"message": "Internal server error"}), 500


# Update an existing task
@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def api_update_task(task_id):
    data = request.json
    if not data:
        return jsonify({"message": "No update data provided"}), 400
    try:
        success = update_task(DATABASE_PATH, task_id, data)
        if success:
            return jsonify({"message": "Task updated successfully"})
        else:
            # Could be task not found or no changes made
            return jsonify({"message": "Task not found or no changes applied"}), 404
    except Exception as e:
        print(f"Error updating task {task_id}: {e}")
        return jsonify({"message": "Internal server error"}), 500

# Delete a task
@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def api_delete_task(task_id):
     try:
        success = delete_task(DATABASE_PATH, task_id)
        if success:
            return jsonify({"message": "Task deleted successfully"})
        else:
            return jsonify({"message": "Task not found"}), 404
     except Exception as e:
        print(f"Error deleting task {task_id}: {e}")
        return jsonify({"message": "Internal server error"}), 500


if __name__ == '__main__':
    init_db(DATABASE_PATH) # Initialize DB on first run
    # Make sure frontend dir exists before trying to serve from it
    frontend_dir_abs = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
    if not os.path.isdir(frontend_dir_abs):
         print(f"Warning: Frontend directory '{frontend_dir_abs}' not found. Static file serving might fail.")
         # Optionally create it: os.makedirs(frontend_dir_abs, exist_ok=True)

    app.run(debug=True, host='0.0.0.0', port=4999) # Listen on all interfaces for RDK access