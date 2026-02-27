"""
Flask Web Application for Nodelink Bonus Simulator
===================================================

Supports:
- PowerUp Bonus Simulation (NLK program)
- Direct Bonus Simulation (NLK + USDN programs)

ARCHITECTURE:
- Single shared hierarchy for both simulations
- Hierarchy can be loaded from CSV cache or generated fresh
- Both simulations operate on the same user base for valid comparison
- Proper state management for web deployment (Render, etc.)
"""

from flask import Flask, render_template, request, jsonify
from mlm_simulation import MLMSimulation, create_default_config
from direct_bonus_simulation import DirectBonusSimulation, create_direct_bonus_config
import threading
import time
import os

app = Flask(__name__)

# ============================================
# SHARED HIERARCHY STATE
# ============================================
hierarchy_state = {
    'users': None,
    'total_users': 0,
    'max_depth': 0,
    'source': None
}

# Simulation states with enhanced tracking
powerup_state = {
    'running': False,
    'progress': 0,
    'status': 'Ready',
    'results': None,
    'error': None,
    'start_time': None,
    'elapsed_seconds': 0,
    'cancel_requested': False
}

direct_bonus_state = {
    'running': False,
    'progress': 0,
    'status': 'Ready',
    'results': None,
    'error': None,
    'start_time': None,
    'elapsed_seconds': 0,
    'cancel_requested': False
}

# Lock for thread-safe state updates
state_lock = threading.Lock()


def reset_powerup_state():
    """Reset PowerUp state to initial values"""
    global powerup_state
    with state_lock:
        powerup_state = {
            'running': False,
            'progress': 0,
            'status': 'Ready',
            'results': None,
            'error': None,
            'start_time': None,
            'elapsed_seconds': 0,
            'cancel_requested': False
        }


def reset_direct_bonus_state():
    """Reset Direct Bonus state to initial values"""
    global direct_bonus_state
    with state_lock:
        direct_bonus_state = {
            'running': False,
            'progress': 0,
            'status': 'Ready',
            'results': None,
            'error': None,
            'start_time': None,
            'elapsed_seconds': 0,
            'cancel_requested': False
        }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/default-config', methods=['GET'])
def get_default_config():
    return jsonify(create_default_config())


@app.route('/api/direct-bonus-config', methods=['GET'])
def get_direct_bonus_config_route():
    return jsonify(create_direct_bonus_config())


@app.route('/api/hierarchy-status', methods=['GET'])
def get_hierarchy_status():
    return jsonify({
        'loaded': hierarchy_state['users'] is not None,
        'total_users': hierarchy_state['total_users'],
        'max_depth': hierarchy_state['max_depth'],
        'source': hierarchy_state['source']
    })


@app.route('/api/run-simulation', methods=['POST'])
def run_simulation():
    global powerup_state
    
    # Check if already running (with timeout protection)
    with state_lock:
        if powerup_state['running']:
            # Check if it's been running too long (stuck state)
            if powerup_state['start_time']:
                elapsed = time.time() - powerup_state['start_time']
                if elapsed > 600:  # 10 minutes timeout
                    # Force reset stuck state
                    pass  # Will reset below
                else:
                    return jsonify({'error': f'PowerUp simulation already running ({int(elapsed)}s elapsed). Please wait or cancel.'}), 400
        
        if direct_bonus_state['running']:
            return jsonify({'error': 'Direct Bonus simulation is running. Please wait.'}), 400
    
    try:
        config = request.json
        if not config:
            return jsonify({'error': 'No configuration provided'}), 400
        
        with state_lock:
            powerup_state['running'] = True
            powerup_state['progress'] = 0
            powerup_state['status'] = 'Starting...'
            powerup_state['results'] = None
            powerup_state['error'] = None
            powerup_state['start_time'] = time.time()
            powerup_state['elapsed_seconds'] = 0
            powerup_state['cancel_requested'] = False
        
        thread = threading.Thread(target=run_powerup_background, args=(config,), daemon=True)
        thread.start()
        return jsonify({'message': 'PowerUp simulation started'})
        
    except Exception as e:
        reset_powerup_state()
        return jsonify({'error': str(e)}), 500


def run_powerup_background(config):
    global powerup_state, hierarchy_state
    
    try:
        def update_status(status, progress=None):
            with state_lock:
                powerup_state['status'] = status
                if progress is not None:
                    powerup_state['progress'] = progress
                if powerup_state['start_time']:
                    powerup_state['elapsed_seconds'] = int(time.time() - powerup_state['start_time'])
                # Check for cancellation
                return powerup_state['cancel_requested']
        
        if update_status('Initializing...', 5):
            raise Exception('Cancelled by user')
        
        sim = MLMSimulation(config)
        
        if update_status('Running simulation...', 10):
            raise Exception('Cancelled by user')
        
        # Run simulation with progress callback
        stats = sim.run_simulation(progress_callback=lambda msg, pct: update_status(msg, pct))
        
        if update_status('Finalizing...', 95):
            raise Exception('Cancelled by user')
        
        # Update shared hierarchy AFTER run_simulation completes
        with state_lock:
            hierarchy_state['users'] = sim.users
            hierarchy_state['total_users'] = len(sim.users)
            hierarchy_state['max_depth'] = config.get('max_depth', 7)
            hierarchy_state['source'] = 'PowerUp'
            
            powerup_state['status'] = 'Complete'
            powerup_state['results'] = stats
            powerup_state['progress'] = 100
            powerup_state['running'] = False
            if powerup_state['start_time']:
                powerup_state['elapsed_seconds'] = int(time.time() - powerup_state['start_time'])
        
    except Exception as e:
        with state_lock:
            powerup_state['status'] = 'Error' if 'Cancel' not in str(e) else 'Cancelled'
            powerup_state['error'] = str(e) if 'Cancel' not in str(e) else None
            powerup_state['running'] = False
            if powerup_state['start_time']:
                powerup_state['elapsed_seconds'] = int(time.time() - powerup_state['start_time'])
        if 'Cancel' not in str(e):
            import traceback
            traceback.print_exc()


@app.route('/api/run-direct-bonus', methods=['POST'])
def run_direct_bonus():
    global direct_bonus_state
    
    # Check if already running (with timeout protection)
    with state_lock:
        if direct_bonus_state['running']:
            if direct_bonus_state['start_time']:
                elapsed = time.time() - direct_bonus_state['start_time']
                if elapsed > 600:  # 10 minutes timeout
                    pass  # Will reset below
                else:
                    return jsonify({'error': f'Direct Bonus simulation already running ({int(elapsed)}s elapsed). Please wait or cancel.'}), 400
        
        if powerup_state['running']:
            return jsonify({'error': 'PowerUp simulation is running. Please wait.'}), 400
    
    try:
        config = request.json
        if not config:
            return jsonify({'error': 'No configuration provided'}), 400
        
        with state_lock:
            direct_bonus_state['running'] = True
            direct_bonus_state['progress'] = 0
            direct_bonus_state['status'] = 'Starting...'
            direct_bonus_state['results'] = None
            direct_bonus_state['error'] = None
            direct_bonus_state['start_time'] = time.time()
            direct_bonus_state['elapsed_seconds'] = 0
            direct_bonus_state['cancel_requested'] = False
        
        thread = threading.Thread(target=run_direct_bonus_background, args=(config,), daemon=True)
        thread.start()
        return jsonify({'message': 'Direct Bonus simulation started'})
        
    except Exception as e:
        reset_direct_bonus_state()
        return jsonify({'error': str(e)}), 500


def run_direct_bonus_background(config):
    global direct_bonus_state, hierarchy_state
    
    try:
        def update_status(status, progress=None):
            with state_lock:
                direct_bonus_state['status'] = status
                if progress is not None:
                    direct_bonus_state['progress'] = progress
                if direct_bonus_state['start_time']:
                    direct_bonus_state['elapsed_seconds'] = int(time.time() - direct_bonus_state['start_time'])
                return direct_bonus_state['cancel_requested']
        
        if update_status('Checking hierarchy...', 5):
            raise Exception('Cancelled by user')
        
        # If no hierarchy, generate one
        if hierarchy_state['users'] is None:
            if update_status('Generating hierarchy...', 10):
                raise Exception('Cancelled by user')
            
            total_users = config.get('hierarchy_total_users', 10000)
            max_depth = config.get('hierarchy_max_depth', 7)
            
            mlm_config = create_default_config()
            mlm_config['total_users'] = total_users
            mlm_config['max_depth'] = max_depth
            mlm_config['use_hierarchy_cache'] = config.get('use_hierarchy_cache', True)
            
            mlm_sim = MLMSimulation(mlm_config)
            mlm_sim.generate_hierarchy(total_users, max_depth)
            
            with state_lock:
                hierarchy_state['users'] = mlm_sim.users
                hierarchy_state['total_users'] = len(mlm_sim.users)
                hierarchy_state['max_depth'] = max_depth
                hierarchy_state['source'] = 'Direct Bonus'
        
        if update_status(f"Simulating {hierarchy_state['total_users']:,} users...", 30):
            raise Exception('Cancelled by user')
        
        # Run Direct Bonus simulation
        db_sim = DirectBonusSimulation(config, hierarchy_state['users'])
        stats = db_sim.run_simulation()
        
        # Add hierarchy info
        stats['hierarchy_info'] = {
            'total_users': hierarchy_state['total_users'],
            'max_depth': hierarchy_state['max_depth'],
            'source': hierarchy_state['source']
        }
        
        with state_lock:
            direct_bonus_state['status'] = 'Complete'
            direct_bonus_state['results'] = stats
            direct_bonus_state['progress'] = 100
            direct_bonus_state['running'] = False
            if direct_bonus_state['start_time']:
                direct_bonus_state['elapsed_seconds'] = int(time.time() - direct_bonus_state['start_time'])
        
    except Exception as e:
        with state_lock:
            direct_bonus_state['status'] = 'Error' if 'Cancel' not in str(e) else 'Cancelled'
            direct_bonus_state['error'] = str(e) if 'Cancel' not in str(e) else None
            direct_bonus_state['running'] = False
            if direct_bonus_state['start_time']:
                direct_bonus_state['elapsed_seconds'] = int(time.time() - direct_bonus_state['start_time'])
        if 'Cancel' not in str(e):
            import traceback
            traceback.print_exc()


@app.route('/api/status', methods=['GET'])
def get_status():
    with state_lock:
        # Update elapsed time if running
        if powerup_state['running'] and powerup_state['start_time']:
            powerup_state['elapsed_seconds'] = int(time.time() - powerup_state['start_time'])
        return jsonify(powerup_state)


@app.route('/api/direct-bonus-status', methods=['GET'])
def get_direct_bonus_status():
    with state_lock:
        # Update elapsed time if running
        if direct_bonus_state['running'] and direct_bonus_state['start_time']:
            direct_bonus_state['elapsed_seconds'] = int(time.time() - direct_bonus_state['start_time'])
        return jsonify(direct_bonus_state)


@app.route('/api/cancel-simulation', methods=['POST'])
def cancel_simulation():
    """Cancel running simulation"""
    global powerup_state, direct_bonus_state
    
    sim_type = request.json.get('type', 'powerup') if request.json else 'powerup'
    
    with state_lock:
        if sim_type == 'powerup':
            if powerup_state['running']:
                powerup_state['cancel_requested'] = True
                powerup_state['status'] = 'Cancelling...'
                return jsonify({'message': 'Cancel requested for PowerUp simulation'})
            else:
                return jsonify({'message': 'No PowerUp simulation running'})
        else:
            if direct_bonus_state['running']:
                direct_bonus_state['cancel_requested'] = True
                direct_bonus_state['status'] = 'Cancelling...'
                return jsonify({'message': 'Cancel requested for Direct Bonus simulation'})
            else:
                return jsonify({'message': 'No Direct Bonus simulation running'})


@app.route('/api/force-reset', methods=['POST'])
def force_reset():
    """Force reset all states (emergency recovery)"""
    global hierarchy_state
    
    reset_powerup_state()
    reset_direct_bonus_state()
    
    # Optionally clear hierarchy too
    if request.json and request.json.get('clear_hierarchy', False):
        hierarchy_state = {
            'users': None,
            'total_users': 0,
            'max_depth': 0,
            'source': None
        }
    
    return jsonify({'message': 'All states reset successfully'})


@app.route('/api/clear-hierarchy', methods=['POST'])
def clear_hierarchy():
    global hierarchy_state
    
    with state_lock:
        if powerup_state['running'] or direct_bonus_state['running']:
            return jsonify({'error': 'Cannot clear while simulation running'}), 400
    
    hierarchy_state = {
        'users': None,
        'total_users': 0,
        'max_depth': 0,
        'source': None
    }
    return jsonify({'message': 'Hierarchy cleared'})


# Health check endpoint for Render
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)