"""
Flask Web Application for MLM Compensation Simulator
=====================================================

Supports:
- PowerUp Bonus Simulation (NLK program)
- Direct Bonus Simulation (NLK + USDN programs)

ARCHITECTURE:
- Single shared hierarchy for both simulations
- Hierarchy can be loaded from CSV cache or generated fresh
- Both simulations operate on the same user base for valid comparison
"""

from flask import Flask, render_template, request, jsonify
from mlm_simulation import MLMSimulation, create_default_config
from direct_bonus_simulation import DirectBonusSimulation, create_direct_bonus_config
import threading

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

# Simulation states
powerup_state = {
    'running': False,
    'progress': 0,
    'status': 'Ready',
    'results': None,
    'error': None
}

direct_bonus_state = {
    'running': False,
    'progress': 0,
    'status': 'Ready',
    'results': None,
    'error': None
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
    
    if powerup_state['running']:
        return jsonify({'error': 'PowerUp simulation already running'}), 400
    if direct_bonus_state['running']:
        return jsonify({'error': 'Direct Bonus simulation is running. Please wait.'}), 400
    
    try:
        config = request.json
        if not config:
            return jsonify({'error': 'No configuration provided'}), 400
        
        powerup_state = {
            'running': True,
            'progress': 0,
            'status': 'Starting...',
            'results': None,
            'error': None
        }
        
        thread = threading.Thread(target=run_powerup_background, args=(config,))
        thread.start()
        return jsonify({'message': 'PowerUp simulation started'})
        
    except Exception as e:
        powerup_state['running'] = False
        powerup_state['error'] = str(e)
        return jsonify({'error': str(e)}), 500


def run_powerup_background(config):
    global powerup_state, hierarchy_state
    
    try:
        powerup_state['status'] = 'Initializing...'
        sim = MLMSimulation(config)
        
        powerup_state['status'] = 'Loading/generating hierarchy...'
        total_users = config.get('total_users', 100000)
        max_depth = config.get('max_depth', 15)
        sim.generate_hierarchy(total_users, max_depth)
        
        # Update shared hierarchy
        hierarchy_state['users'] = sim.users
        hierarchy_state['total_users'] = len(sim.users)
        hierarchy_state['max_depth'] = max_depth
        hierarchy_state['source'] = 'PowerUp'
        
        powerup_state['status'] = 'Running simulation...'
        stats = sim.run_simulation()
        
        powerup_state['status'] = 'Complete'
        powerup_state['results'] = stats
        powerup_state['progress'] = 100
        powerup_state['running'] = False
        
    except Exception as e:
        powerup_state['status'] = 'Error'
        powerup_state['error'] = str(e)
        powerup_state['running'] = False
        import traceback
        traceback.print_exc()


@app.route('/api/run-direct-bonus', methods=['POST'])
def run_direct_bonus():
    global direct_bonus_state
    
    if direct_bonus_state['running']:
        return jsonify({'error': 'Direct Bonus simulation already running'}), 400
    if powerup_state['running']:
        return jsonify({'error': 'PowerUp simulation is running. Please wait.'}), 400
    
    try:
        config = request.json
        if not config:
            return jsonify({'error': 'No configuration provided'}), 400
        
        direct_bonus_state = {
            'running': True,
            'progress': 0,
            'status': 'Starting...',
            'results': None,
            'error': None
        }
        
        thread = threading.Thread(target=run_direct_bonus_background, args=(config,))
        thread.start()
        return jsonify({'message': 'Direct Bonus simulation started'})
        
    except Exception as e:
        direct_bonus_state['running'] = False
        direct_bonus_state['error'] = str(e)
        return jsonify({'error': str(e)}), 500


def run_direct_bonus_background(config):
    global direct_bonus_state, hierarchy_state
    
    try:
        direct_bonus_state['status'] = 'Checking hierarchy...'
        
        # If no hierarchy, generate one
        if hierarchy_state['users'] is None:
            direct_bonus_state['status'] = 'Generating hierarchy...'
            
            total_users = config.get('hierarchy_total_users', 100000)
            max_depth = config.get('hierarchy_max_depth', 15)
            
            mlm_config = create_default_config()
            mlm_config['total_users'] = total_users
            mlm_config['max_depth'] = max_depth
            mlm_config['use_hierarchy_cache'] = config.get('use_hierarchy_cache', True)
            
            mlm_sim = MLMSimulation(mlm_config)
            mlm_sim.generate_hierarchy(total_users, max_depth)
            
            hierarchy_state['users'] = mlm_sim.users
            hierarchy_state['total_users'] = len(mlm_sim.users)
            hierarchy_state['max_depth'] = max_depth
            hierarchy_state['source'] = 'Direct Bonus'
        
        direct_bonus_state['status'] = f"Simulating {hierarchy_state['total_users']:,} users..."
        
        # Run Direct Bonus simulation
        db_sim = DirectBonusSimulation(config, hierarchy_state['users'])
        stats = db_sim.run_simulation()
        
        # Add hierarchy info
        stats['hierarchy_info'] = {
            'total_users': hierarchy_state['total_users'],
            'max_depth': hierarchy_state['max_depth'],
            'source': hierarchy_state['source']
        }
        
        direct_bonus_state['status'] = 'Complete'
        direct_bonus_state['results'] = stats
        direct_bonus_state['progress'] = 100
        direct_bonus_state['running'] = False
        
    except Exception as e:
        direct_bonus_state['status'] = 'Error'
        direct_bonus_state['error'] = str(e)
        direct_bonus_state['running'] = False
        import traceback
        traceback.print_exc()


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(powerup_state)


@app.route('/api/direct-bonus-status', methods=['GET'])
def get_direct_bonus_status():
    return jsonify(direct_bonus_state)


@app.route('/api/clear-hierarchy', methods=['POST'])
def clear_hierarchy():
    global hierarchy_state
    
    if powerup_state['running'] or direct_bonus_state['running']:
        return jsonify({'error': 'Cannot clear while simulation running'}), 400
    
    hierarchy_state = {
        'users': None,
        'total_users': 0,
        'max_depth': 0,
        'source': None
    }
    return jsonify({'message': 'Hierarchy cleared'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)