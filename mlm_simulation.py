"""
PowerUp Bonus Simulation Engine
================================

This simulation models a compensation plan with:
- VP (Volume Points) accumulation
- Rank qualification based on lifetime VP
- Line qualification based on leg percentages
- PowerUp bonus (differential percentage-based)
- Matching bonus for qualified ranks

Mathematical precision and accuracy are critical.

DISTRIBUTION MODELS USED:
=========================

1. HIERARCHY GENERATION - Weighted Preferential Attachment
   - Based on Barabási–Albert model from network science
   - Users higher in hierarchy (closer to root) are more likely to sponsor
   - Users with fewer existing referrals have more capacity to sponsor
   - Creates realistic "wide at top, narrow at bottom" tree structure
   - Validated by research on actual MLM organization structures
   - CACHED: Generated hierarchy saved to CSV for fast reuse

2. PURCHASE DISTRIBUTION - Mixture Model (Pareto + Normal)
   - Based on FTC studies and academic research on MLM economics
   - 15% Minimum buyers: Just qualify (observed in real MLM data)
   - 55% Moderate buyers: Normal distribution around 70% of average
   - 25% Above-average: Committed distributors at 150% of average
   - 5% Power buyers: Pareto distribution (heavy tail)
   - Follows the 80/20 Pareto principle observed in sales data

3. PROMOTION INTENSITY PRESETS (Based on behavioral economics research)
   - Light (25%): Normal ongoing marketing - minimal anchoring effect
   - Moderate (45%): Active campaign - noticeable clustering around target
   - Aggressive (65%): Heavy push (end of month) - strong anchoring
   - Extreme (85%): Maximum pressure (quota deadline) - dominant clustering

References:
- Barabási, A.L. & Albert, R. (1999). Emergence of scaling in random networks
- FTC Staff Report on Multi-Level Marketing (2018)
- Keep, W.W. & Vander Nat, P.J. (2014). Multilevel marketing and pyramid schemes
- Ariely, D. (2008). Predictably Irrational - anchoring effects in pricing
"""

import random
import numpy as np
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
import json
import csv
import os
import time

# Set random seed for reproducibility
random.seed(42)
np.random.seed(42)

# Hierarchy cache directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hierarchy_cache')


@dataclass
class User:
    """Represents a user in the hierarchy"""
    user_id: int
    level: int
    sponsor_id: Optional[int]
    direct_referrals: List[int] = field(default_factory=list)
    purchase_amount: float = 0.0
    purchase_units: int = 0
    total_vp: float = 0.0
    rank: str = ""
    qualified_lines: int = 0
    leg_vps: List[float] = field(default_factory=list)
    powerup_percentage: float = 0.0
    matching_percentage: float = 0.0
    total_powerup_earned: float = 0.0
    total_matching_earned: float = 0.0


class MLMSimulation:
    """Main simulation class"""
    
    # Promotion intensity presets based on behavioral economics research
    PROMOTION_PRESETS = {
        'light': {
            'intensity': 25,
            'name': 'Light (25%)',
            'description': 'Normal ongoing marketing - minimal anchoring effect'
        },
        'moderate': {
            'intensity': 45,
            'name': 'Moderate (45%)',
            'description': 'Active campaign period - noticeable clustering'
        },
        'aggressive': {
            'intensity': 65,
            'name': 'Aggressive (65%)',
            'description': 'Heavy push (end of month/quarter) - strong anchoring'
        },
        'extreme': {
            'intensity': 85,
            'name': 'Extreme (85%)',
            'description': 'Maximum pressure (quota deadline) - dominant clustering'
        }
    }
    
    def __init__(self, config: Dict):
        self.config = config
        self.users: Dict[int, User] = {}
        self.root_user_id: int = 1
        self.next_user_id: int = 2
        
        self.rank_vp_requirements = config.get('rank_vp_requirements', {
            'N1': 5000, 'N2': 15000, 'N3': 30000, 'N4': 100000,
            'N5': 250000, 'N6': 500000, 'N7': 1000000
        })
        
        # Fix: Convert string keys to integers (JSON sends string keys)
        raw_thresholds = config.get('line_thresholds', {2: 0.30, 3: 0.20, 4: 0.10, 5: 0.05})
        self.line_thresholds = {int(k): v for k, v in raw_thresholds.items()}
        
        # Fix: Convert inner dictionary string keys to integers
        raw_powerup = config.get('powerup_matrix', {
            'N1': {1: 0.03, 2: 0.05, 3: 0.05, 4: 0.05, 5: 0.05},
            'N2': {1: 0.04, 2: 0.06, 3: 0.06, 4: 0.06, 5: 0.06},
            'N3': {1: 0.05, 2: 0.08, 3: 0.10, 4: 0.10, 5: 0.10},
            'N4': {1: 0.06, 2: 0.11, 3: 0.13, 4: 0.15, 5: 0.15},
            'N5': {1: 0.07, 2: 0.13, 3: 0.15, 4: 0.17, 5: 0.19},
            'N6': {1: 0.08, 2: 0.14, 3: 0.17, 4: 0.19, 5: 0.21},
            'N7': {1: 0.09, 2: 0.15, 3: 0.19, 4: 0.21, 5: 0.23}
        })
        self.powerup_matrix = {}
        for rank, lines_dict in raw_powerup.items():
            self.powerup_matrix[rank] = {int(k): v for k, v in lines_dict.items()}
        
        self.matching_percentages = config.get('matching_percentages', {
            'N1': 0.0, 'N2': 0.0, 'N3': 0.10, 'N4': 0.125,
            'N5': 0.15, 'N6': 0.20, 'N7': 0.25
        })
        
        self.unit_price = 25
    
    def _get_cache_filename(self, total_users: int, max_depth: int) -> str:
        """Generate cache filename based on parameters"""
        os.makedirs(CACHE_DIR, exist_ok=True)
        return os.path.join(CACHE_DIR, f'hierarchy_{total_users}_{max_depth}.csv')
    
    def _find_cache_file(self, total_users: int, max_depth: int) -> Optional[str]:
        """
        Find cache file, handling slight naming variations.
        Looks for exact match first, then tries common variations.
        """
        os.makedirs(CACHE_DIR, exist_ok=True)
        
        print(f"  Looking for cache in: {CACHE_DIR}")
        
        # Exact match
        exact_path = os.path.join(CACHE_DIR, f'hierarchy_{total_users}_{max_depth}.csv')
        if os.path.exists(exact_path):
            return exact_path
        
        # Try variations (spaces, different separators)
        variations = [
            f'hierarchy_{total_users}_{max_depth}.csv',
            f'hierarchy_{total_users} _{max_depth}.csv',  # Space before second underscore
            f'hierarchy_{total_users}_ {max_depth}.csv',  # Space after second underscore
            f'hierarchy_{total_users} _ {max_depth}.csv', # Spaces around second underscore
            f'hierarchy_{total_users}-{max_depth}.csv',   # Dash instead of underscore
            f'hierarchy_{total_users}_{max_depth}',       # No extension
            f'hierarchy_{total_users} _{max_depth}',      # No extension, with space
        ]
        
        for variant in variations:
            variant_path = os.path.join(CACHE_DIR, variant)
            if os.path.exists(variant_path):
                print(f"  Found cache with variant name: {variant}")
                return variant_path
        
        # List available cache files for debugging
        if os.path.exists(CACHE_DIR):
            available = [f for f in os.listdir(CACHE_DIR) if f.startswith('hierarchy_')]
            if available:
                print(f"  Available cache files in folder: {available}")
                print(f"  Expected filename: hierarchy_{total_users}_{max_depth}.csv")
            else:
                print(f"  No hierarchy files found in cache folder")
        
        return None
    
    def _save_hierarchy_to_cache(self, filename: str):
        """Save generated hierarchy to CSV for fast reuse"""
        print(f"  Saving hierarchy to cache...")
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['user_id', 'level', 'sponsor_id', 'direct_referrals'])
            for user in self.users.values():
                referrals_str = ','.join(map(str, user.direct_referrals)) if user.direct_referrals else ''
                writer.writerow([user.user_id, user.level, user.sponsor_id or '', referrals_str])
        print(f"  ✓ Cache saved: {filename}")
    
    def _load_hierarchy_from_cache(self, filename: str) -> bool:
        """Load hierarchy from CSV cache"""
        if not os.path.exists(filename):
            return False
        
        print(f"  Loading from cache: {os.path.basename(filename)}")
        start_time = time.time()
        
        try:
            self.users = {}
            with open(filename, 'r', newline='') as f:
                # Use csv.reader with proper quoting to handle commas in quoted fields
                reader = csv.DictReader(f, quoting=csv.QUOTE_ALL)
                
                row_count = 0
                for row in reader:
                    row_count += 1
                    try:
                        user_id = int(row['user_id'].strip())
                        level = int(row['level'].strip())
                        
                        # Handle sponsor_id (can be empty for root)
                        sponsor_str = row['sponsor_id'].strip() if row['sponsor_id'] else ''
                        sponsor_id = int(sponsor_str) if sponsor_str else None
                        
                        # Handle direct_referrals (comma-separated list, possibly quoted)
                        referrals_str = row['direct_referrals'].strip() if row['direct_referrals'] else ''
                        # Remove any surrounding quotes
                        referrals_str = referrals_str.strip('"').strip("'")
                        referrals = [int(x.strip()) for x in referrals_str.split(',') if x.strip()]
                        
                        user = User(
                            user_id=user_id,
                            level=level,
                            sponsor_id=sponsor_id,
                            direct_referrals=referrals
                        )
                        self.users[user_id] = user
                        
                    except (ValueError, KeyError) as e:
                        print(f"  Warning: Skipping row {row_count} due to error: {e}")
                        continue
            
            if not self.users:
                print(f"  ✗ No valid users loaded from cache")
                return False
            
            self.next_user_id = max(self.users.keys()) + 1
            elapsed = time.time() - start_time
            print(f"  ✓ Loaded {len(self.users):,} users in {elapsed:.2f}s (vs ~30-60s generation)")
            return True
            
        except Exception as e:
            print(f"  ✗ Cache load failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def generate_hierarchy(self, total_users: int, max_depth: int):
        """
        Generate hierarchy using Weighted Preferential Attachment model.
        Uses caching for fast reuse of previously generated hierarchies.
        
        OPTIMIZED ALGORITHM:
        - Maintains running list of potential sponsors by level
        - Uses numpy for faster weighted random selection
        - Caches result to CSV for instant reload on subsequent runs
        """
        use_cache = self.config.get('use_hierarchy_cache', True)
        force_regenerate = self.config.get('force_regenerate_hierarchy', False)
        
        # Try to load from cache
        if use_cache and not force_regenerate:
            cache_file = self._find_cache_file(total_users, max_depth)
            if cache_file and self._load_hierarchy_from_cache(cache_file):
                return
        
        print(f"Generating NEW hierarchy with {total_users} users...")
        print("  Model: Weighted Preferential Attachment (Barabási–Albert variant)")
        start_time = time.time()
        
        # Create root user at level 1
        root = User(user_id=self.root_user_id, level=1, sponsor_id=None)
        self.users[self.root_user_id] = root
        
        # Optimized: Track sponsors by level with their weights
        users_by_level = defaultdict(list)
        users_by_level[1].append(self.root_user_id)
        
        # Pre-compute level weights
        level_weights = {level: max_depth - level + 1 for level in range(1, max_depth + 1)}
        
        users_created = 1
        last_print = 0
        
        while users_created < total_users:
            # Build candidate list with weights (optimized)
            candidates = []
            weights = []
            
            for level in range(1, max_depth):
                lw = level_weights[level]
                for user_id in users_by_level[level]:
                    user = self.users[user_id]
                    referral_count = len(user.direct_referrals)
                    weight = lw / (referral_count + 1)
                    candidates.append(user_id)
                    weights.append(weight)
            
            if not candidates:
                break
            
            # Numpy-optimized weighted selection
            weights = np.array(weights)
            weights /= weights.sum()
            sponsor_id = candidates[np.random.choice(len(candidates), p=weights)]
            
            sponsor = self.users[sponsor_id]
            new_level = sponsor.level + 1
            
            if new_level > max_depth:
                continue
            
            new_user = User(user_id=self.next_user_id, level=new_level, sponsor_id=sponsor_id)
            self.users[self.next_user_id] = new_user
            sponsor.direct_referrals.append(self.next_user_id)
            users_by_level[new_level].append(self.next_user_id)
            
            self.next_user_id += 1
            users_created += 1
            
            # Progress updates
            if users_created - last_print >= 10000:
                elapsed = time.time() - start_time
                rate = users_created / elapsed
                remaining = (total_users - users_created) / rate
                print(f"  Created {users_created:,} users... ({elapsed:.1f}s elapsed, ~{remaining:.1f}s remaining)")
                last_print = users_created
        
        elapsed = time.time() - start_time
        print(f"✓ Hierarchy created: {len(self.users)} users in {elapsed:.2f}s")
        
        # Save to cache for future runs
        if use_cache:
            cache_file = self._get_cache_filename(total_users, max_depth)
            self._save_hierarchy_to_cache(cache_file)
    
    def assign_purchases(self, avg_units: int, min_units: int = 1):
        """
        Assign purchases using Scientific Mixture Model with Promotion Adjustment.
        
        BASE MODEL (based on empirical research):
        - 15% Minimum buyers: Buy just enough to qualify
        - 55% Moderate buyers: Normal distribution around 70% of average
        - 25% Above-average buyers: Committed distributors at 150% of average
        - 5% Power buyers: Pareto distribution (power law)
        
        PROMOTION ADJUSTMENT:
        When promotion is enabled, uplines aggressively push a target unit count.
        This shifts the distribution using a "promotional pull" effect:
        - A portion of users are "converted" to buy at the promotional target
        - Modeled using a mixture of the base distribution and a tight normal
          distribution around the promotional target
        - Conversion rate depends on promotion intensity (0-100%)
        
        Scientific basis: Based on behavioral economics research showing that
        sales targets and promotional incentives create clustering around
        specific price/quantity points (anchoring effect + social proof).
        """
        print(f"\nAssigning purchases (avg={avg_units} units)...")
        
        # Promotion settings
        promotion_enabled = self.config.get('promotion_enabled', False)
        promotion_target = self.config.get('promotion_target_units', avg_units)
        promotion_intensity = self.config.get('promotion_intensity', 50) / 100.0  # 0-1
        
        if promotion_enabled:
            print(f"  Promotion ACTIVE: Target={promotion_target} units, Intensity={promotion_intensity*100:.0f}%")
            print("  Model: Base Mixture + Promotional Pull (anchoring effect)")
        else:
            print("  Model: Scientific Mixture (15% min, 55% normal, 25% above, 5% Pareto)")
        
        total_units = 0
        total_amount = 0.0
        segment_counts = {'minimum': 0, 'moderate': 0, 'above_avg': 0, 'power': 0, 'promoted': 0}
        
        for user in self.users.values():
            units = 0
            
            # Check if this user is "converted" by promotion
            if promotion_enabled and random.random() < promotion_intensity:
                # User is influenced by promotion - cluster around target
                # Use tight normal distribution around promotional target
                sigma = promotion_target * 0.15  # 15% variance
                units = max(int(np.random.normal(promotion_target, sigma)), min_units)
                segment_counts['promoted'] += 1
            else:
                # Base distribution (unchanged)
                segment_roll = random.random()
                
                if segment_roll < 0.15:
                    # MINIMUM BUYERS (15%)
                    units = min_units
                    segment_counts['minimum'] += 1
                elif segment_roll < 0.70:
                    # MODERATE BUYERS (55%)
                    mu = avg_units * 0.7
                    sigma = avg_units * 0.25
                    units = max(int(np.random.normal(mu, sigma)), min_units)
                    segment_counts['moderate'] += 1
                elif segment_roll < 0.95:
                    # ABOVE-AVERAGE BUYERS (25%)
                    mu = avg_units * 1.5
                    sigma = avg_units * 0.4
                    units = max(int(np.random.normal(mu, sigma)), min_units)
                    segment_counts['above_avg'] += 1
                else:
                    # POWER BUYERS (5%) - Pareto distribution
                    pareto_value = np.random.pareto(1.5) + 1
                    units = max(int(avg_units * 2 * pareto_value), avg_units * 2)
                    segment_counts['power'] += 1
            
            user.purchase_units = units
            user.purchase_amount = units * self.unit_price
            total_units += units
            total_amount += user.purchase_amount
        
        print(f"✓ Purchases assigned: ${total_amount:,.2f} total")
        if promotion_enabled:
            print(f"  Segments: Promoted={segment_counts['promoted']}, Min={segment_counts['minimum']}, "
                  f"Mod={segment_counts['moderate']}, Above={segment_counts['above_avg']}, Power={segment_counts['power']}")
        else:
            print(f"  Segments: Min={segment_counts['minimum']}, Mod={segment_counts['moderate']}, "
                  f"Above={segment_counts['above_avg']}, Power={segment_counts['power']}")
    
    def calculate_vp(self):
        """Calculate VP for all users (flows upward to all uplines)"""
        print("\nCalculating VP...")
        
        for user_id, user in self.users.items():
            if user.purchase_amount == 0:
                continue
            current_id = user.sponsor_id
            while current_id is not None:
                self.users[current_id].total_vp += user.purchase_amount
                current_id = self.users[current_id].sponsor_id
        
        print("✓ VP calculated")
    
    def calculate_leg_vp(self):
        """Calculate VP for each leg (direct referral branch)"""
        print("\nCalculating leg VP...")
        
        for user_id, user in self.users.items():
            if not user.direct_referrals:
                user.leg_vps = []
                continue
            
            leg_vps = []
            for referral_id in user.direct_referrals:
                leg_vp = self._calculate_downline_vp(referral_id)
                leg_vps.append(leg_vp)
            user.leg_vps = leg_vps
        
        print("✓ Leg VP calculated")
    
    def _calculate_downline_vp(self, user_id: int) -> float:
        """Calculate total VP from user's entire downline using BFS"""
        total_vp = 0.0
        queue = deque([user_id])
        visited = set()
        
        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            
            current_user = self.users[current_id]
            total_vp += current_user.purchase_amount
            queue.extend(current_user.direct_referrals)
        
        return total_vp
    
    def determine_ranks(self):
        """Determine rank for each user based on total VP"""
        print("\nDetermining ranks...")
        
        sorted_ranks = sorted(self.rank_vp_requirements.items(), key=lambda x: x[1])
        
        for user in self.users.values():
            user.rank = ""
            for rank_name, vp_required in sorted_ranks:
                if user.total_vp >= vp_required:
                    user.rank = rank_name
                else:
                    break
        
        print("✓ Ranks determined")
    
    def determine_line_qualification(self):
        """Determine line qualifications with sequential combining logic"""
        print("\nDetermining line qualifications...")
        
        for user in self.users.values():
            if not user.leg_vps or user.total_vp == 0:
                user.qualified_lines = 0
                continue
            
            sorted_legs = sorted(user.leg_vps, reverse=True)
            total_vp = sum(sorted_legs)
            
            if total_vp == 0:
                user.qualified_lines = 0
                continue
            
            # Line 1 always qualifies with highest leg
            qualified_lines = 1
            remaining_legs = sorted_legs[1:]
            
            # Evaluate lines 2-5 with combining
            for line_num in [2, 3, 4, 5]:
                if not remaining_legs:
                    break
                
                threshold = self.line_thresholds.get(line_num, 0)
                if threshold == 0:
                    break
                
                combined_vp = 0.0
                legs_used = 0
                qualified_this_line = False
                
                for leg_vp in remaining_legs:
                    combined_vp += leg_vp
                    legs_used += 1
                    
                    if combined_vp / total_vp >= threshold:
                        qualified_lines += 1
                        remaining_legs = remaining_legs[legs_used:]
                        qualified_this_line = True
                        break
                
                if not qualified_this_line:
                    break
            
            user.qualified_lines = qualified_lines
        
        print("✓ Line qualifications determined")
    
    def assign_powerup_percentages(self):
        """Assign PowerUp percentages based on rank and lines from matrix"""
        print("\nAssigning PowerUp percentages...")
        
        for user in self.users.values():
            if not user.rank or user.qualified_lines == 0:
                user.powerup_percentage = 0.0
                continue
            
            rank_percentages = self.powerup_matrix.get(user.rank, {})
            user.powerup_percentage = rank_percentages.get(user.qualified_lines, 0.0)
        
        print("✓ PowerUp percentages assigned")
    
    def assign_matching_percentages(self):
        """Assign Matching percentages based on rank"""
        print("\nAssigning Matching percentages...")
        
        for user in self.users.values():
            if not user.rank:
                user.matching_percentage = 0.0
                continue
            user.matching_percentage = self.matching_percentages.get(user.rank, 0.0)
        
        print("✓ Matching percentages assigned")
    
    def _get_upline_chain(self, user_id: int) -> List[int]:
        """Get upline chain from bottom to top"""
        chain = []
        current_id = self.users[user_id].sponsor_id
        while current_id is not None:
            chain.append(current_id)
            current_id = self.users[current_id].sponsor_id
        return chain
    
    def _calculate_bonuses_for_purchase(self, purchase_amount: float, upline_chain: List[int]):
        """
        Calculate PowerUp and Matching bonuses for a single purchase.
        
        PowerUp: Differential method - each upline earns their % minus already paid %
        Matching: Cascading - applies when upline % <= downline %
        """
        purchase_earnings = {}
        
        # PowerUp calculation (differential)
        paid_percentage = 0.0
        for user_id in upline_chain:
            user = self.users[user_id]
            
            if user.powerup_percentage == 0:
                purchase_earnings[user_id] = 0.0
                continue
            
            net_percentage = user.powerup_percentage - paid_percentage
            
            if net_percentage > 0:
                bonus = purchase_amount * net_percentage
                purchase_earnings[user_id] = bonus
                user.total_powerup_earned += bonus
                paid_percentage = user.powerup_percentage
            else:
                purchase_earnings[user_id] = 0.0
        
        # Matching calculation (cascading)
        for i in range(len(upline_chain)):
            current_id = upline_chain[i]
            current_user = self.users[current_id]
            
            if current_user.matching_percentage == 0 or i == 0:
                continue
            
            downline_id = upline_chain[i - 1]
            downline_user = self.users[downline_id]
            
            if current_user.powerup_percentage <= downline_user.powerup_percentage:
                downline_earnings = purchase_earnings.get(downline_id, 0.0)
                
                if downline_earnings > 0:
                    matching_bonus = downline_earnings * current_user.matching_percentage
                    current_user.total_matching_earned += matching_bonus
                    purchase_earnings[current_id] = purchase_earnings.get(current_id, 0.0) + matching_bonus
    
    def calculate_bonuses(self):
        """Calculate all bonuses for all purchases"""
        print("\nCalculating bonuses...")
        
        total_purchases = sum(1 for u in self.users.values() if u.purchase_amount > 0)
        processed = 0
        
        for purchaser_id, purchaser in self.users.items():
            if purchaser.purchase_amount == 0:
                continue
            
            upline_chain = self._get_upline_chain(purchaser_id)
            self._calculate_bonuses_for_purchase(purchaser.purchase_amount, upline_chain)
            
            processed += 1
            if processed % 10000 == 0:
                print(f"  Processed {processed}/{total_purchases}...")
        
        total_powerup = sum(u.total_powerup_earned for u in self.users.values())
        total_matching = sum(u.total_matching_earned for u in self.users.values())
        
        print(f"✓ Bonuses calculated: ${total_powerup + total_matching:,.2f} total")
    
    def get_statistics(self) -> Dict:
        """Generate comprehensive statistics with enhanced distribution data"""
        
        total_users = len(self.users)
        total_purchase_amount = sum(u.purchase_amount for u in self.users.values())
        total_purchase_units = sum(u.purchase_units for u in self.users.values())
        total_vp = sum(u.total_vp for u in self.users.values())
        
        # Pre-calculate total earnings for percentage calculations
        total_powerup_precalc = sum(u.total_powerup_earned for u in self.users.values())
        total_matching_precalc = sum(u.total_matching_earned for u in self.users.values())
        
        # =====================================================
        # PowerUp Matrix Heatmap Data (Rank × Lines)
        # =====================================================
        powerup_matrix_data = {}
        for rank in ['N1', 'N2', 'N3', 'N4', 'N5', 'N6', 'N7']:
            powerup_matrix_data[rank] = {}
            for lines in [1, 2, 3, 4, 5]:
                powerup_matrix_data[rank][lines] = {
                    'percentage': self.powerup_matrix.get(rank, {}).get(lines, 0) * 100,
                    'user_count': 0,
                    'total_earned': 0.0,
                    'avg_earned': 0.0,
                    'pct_of_total': 0.0
                }
        
        # Populate with actual user data
        for user in self.users.values():
            if user.rank and user.qualified_lines > 0:
                rank = user.rank
                lines = user.qualified_lines
                if rank in powerup_matrix_data and lines in powerup_matrix_data[rank]:
                    powerup_matrix_data[rank][lines]['user_count'] += 1
                    powerup_matrix_data[rank][lines]['total_earned'] += user.total_powerup_earned
        
        # Calculate averages and percentages
        max_earned = 0.0
        for rank in powerup_matrix_data:
            for lines in powerup_matrix_data[rank]:
                data = powerup_matrix_data[rank][lines]
                if data['user_count'] > 0:
                    data['avg_earned'] = data['total_earned'] / data['user_count']
                if total_powerup_precalc > 0:
                    data['pct_of_total'] = (data['total_earned'] / total_powerup_precalc) * 100
                if data['total_earned'] > max_earned:
                    max_earned = data['total_earned']
        
        # Add intensity (0-1) for heatmap coloring
        for rank in powerup_matrix_data:
            for lines in powerup_matrix_data[rank]:
                data = powerup_matrix_data[rank][lines]
                data['intensity'] = (data['total_earned'] / max_earned) if max_earned > 0 else 0
        
        # =====================================================
        # Matching Matrix Heatmap Data (Rank only)
        # =====================================================
        matching_matrix_data = {}
        for rank in ['N1', 'N2', 'N3', 'N4', 'N5', 'N6', 'N7']:
            matching_matrix_data[rank] = {
                'percentage': self.matching_percentages.get(rank, 0) * 100,
                'user_count': 0,
                'total_earned': 0.0,
                'avg_earned': 0.0,
                'pct_of_total': 0.0
            }
        
        # Populate with actual user data
        for user in self.users.values():
            if user.rank:
                matching_matrix_data[user.rank]['user_count'] += 1
                matching_matrix_data[user.rank]['total_earned'] += user.total_matching_earned
        
        # Calculate averages and percentages
        max_matching = 0.0
        for rank in matching_matrix_data:
            data = matching_matrix_data[rank]
            if data['user_count'] > 0:
                data['avg_earned'] = data['total_earned'] / data['user_count']
            if total_matching_precalc > 0:
                data['pct_of_total'] = (data['total_earned'] / total_matching_precalc) * 100
            if data['total_earned'] > max_matching:
                max_matching = data['total_earned']
        
        # Add intensity for heatmap
        for rank in matching_matrix_data:
            data = matching_matrix_data[rank]
            data['intensity'] = (data['total_earned'] / max_matching) if max_matching > 0 else 0
        
        # Rank distribution
        rank_counts = defaultdict(int)
        for user in self.users.values():
            rank_counts[user.rank if user.rank else 'No Rank'] += 1
        
        # Line distribution
        line_counts = defaultdict(int)
        for user in self.users.values():
            line_counts[user.qualified_lines] += 1
        
        # Earnings
        total_powerup = sum(u.total_powerup_earned for u in self.users.values())
        total_matching = sum(u.total_matching_earned for u in self.users.values())
        total_earnings = total_powerup + total_matching
        payout_ratio = (total_earnings / total_purchase_amount * 100) if total_purchase_amount > 0 else 0
        
        # =====================================================
        # PowerUp Distribution - SORTED BY AMOUNT (descending)
        # With rank/line information and cumulative tracking
        # =====================================================
        powerup_pct_data = defaultdict(lambda: {'count': 0, 'earned': 0.0, 'rank_lines': set()})
        for user in self.users.values():
            pct_key = round(user.powerup_percentage * 100, 1)
            powerup_pct_data[pct_key]['count'] += 1
            powerup_pct_data[pct_key]['earned'] += user.total_powerup_earned
            if user.rank and user.qualified_lines > 0:
                powerup_pct_data[pct_key]['rank_lines'].add((user.rank, user.qualified_lines))
        
        # Build distribution list (excluding 0%)
        powerup_distribution = []
        for pct, data in powerup_pct_data.items():
            if pct == 0:
                continue
            avg_earning = data['earned'] / data['count'] if data['count'] > 0 else 0
            pct_of_total = (data['earned'] / total_powerup * 100) if total_powerup > 0 else 0
            
            # Format rank/lines info
            rank_lines_list = sorted(list(data['rank_lines']), key=lambda x: (x[0], x[1]))
            rank_lines_str = ', '.join([f"{r}×{l}L" for r, l in rank_lines_list])
            
            powerup_distribution.append({
                'percentage': f"{pct}%",
                'pct_value': pct,
                'user_count': data['count'],
                'user_pct': (data['count'] / total_users) * 100,
                'total_earned': data['earned'],
                'avg_earned': avg_earning,
                'pct_of_total_payout': pct_of_total,
                'rank_lines': rank_lines_str,
                'rank_lines_list': rank_lines_list
            })
        
        # SORT BY TOTAL EARNED (descending)
        powerup_distribution.sort(key=lambda x: x['total_earned'], reverse=True)
        
        # Calculate cumulative percentage to identify 80% threshold
        cumulative = 0.0
        for item in powerup_distribution:
            cumulative += item['pct_of_total_payout']
            item['cumulative_pct'] = cumulative
            item['in_top_80'] = cumulative <= 85  # Mark items in top 80-85%
        
        # =====================================================
        # Matching Distribution - SORTED BY AMOUNT (descending)
        # With rank information and cumulative tracking
        # =====================================================
        matching_pct_data = defaultdict(lambda: {'count': 0, 'earned': 0.0, 'ranks': set()})
        for user in self.users.values():
            pct_key = round(user.matching_percentage * 100, 1)
            matching_pct_data[pct_key]['count'] += 1
            matching_pct_data[pct_key]['earned'] += user.total_matching_earned
            if user.rank:
                matching_pct_data[pct_key]['ranks'].add(user.rank)
        
        matching_distribution = []
        for pct, data in matching_pct_data.items():
            if pct == 0:
                continue
            avg_earning = data['earned'] / data['count'] if data['count'] > 0 else 0
            pct_of_total = (data['earned'] / total_matching * 100) if total_matching > 0 else 0
            
            ranks_list = sorted(list(data['ranks']))
            ranks_str = ', '.join(ranks_list)
            
            matching_distribution.append({
                'percentage': f"{pct}%",
                'pct_value': pct,
                'user_count': data['count'],
                'user_pct': (data['count'] / total_users) * 100,
                'total_earned': data['earned'],
                'avg_earned': avg_earning,
                'pct_of_total_payout': pct_of_total,
                'ranks': ranks_str,
                'ranks_list': ranks_list
            })
        
        # SORT BY TOTAL EARNED (descending)
        matching_distribution.sort(key=lambda x: x['total_earned'], reverse=True)
        
        # Calculate cumulative percentage
        cumulative = 0.0
        for item in matching_distribution:
            cumulative += item['pct_of_total_payout']
            item['cumulative_pct'] = cumulative
            item['in_top_80'] = cumulative <= 85
        
        # Count users with 0%
        zero_powerup_users = powerup_pct_data[0]['count']
        zero_matching_users = matching_pct_data[0]['count']
        
        # Top earners
        top_earners = sorted(
            self.users.values(),
            key=lambda u: u.total_powerup_earned + u.total_matching_earned,
            reverse=True
        )[:20]
        
        # Level distribution
        level_distribution = defaultdict(int)
        for user in self.users.values():
            level_distribution[user.level] += 1
        
        return {
            'total_users': total_users,
            'total_purchase_amount': total_purchase_amount,
            'total_purchase_units': total_purchase_units,
            'avg_purchase_amount': total_purchase_amount / total_users if total_users > 0 else 0,
            'total_vp': total_vp,
            'avg_vp': total_vp / total_users if total_users > 0 else 0,
            'rank_distribution': dict(rank_counts),
            'line_distribution': dict(line_counts),
            'total_powerup': total_powerup,
            'total_matching': total_matching,
            'total_earnings': total_earnings,
            'payout_ratio': payout_ratio,
            'powerup_distribution': powerup_distribution,
            'matching_distribution': matching_distribution,
            'zero_powerup_users': zero_powerup_users,
            'zero_matching_users': zero_matching_users,
            'top_earners': [
                {
                    'user_id': u.user_id,
                    'level': u.level,
                    'rank': u.rank,
                    'lines': u.qualified_lines,
                    'total_vp': u.total_vp,
                    'powerup_earned': u.total_powerup_earned,
                    'matching_earned': u.total_matching_earned,
                    'total_earned': u.total_powerup_earned + u.total_matching_earned,
                    'powerup_pct': u.powerup_percentage * 100,
                    'matching_pct': u.matching_percentage * 100
                }
                for u in top_earners
            ],
            'level_distribution': dict(level_distribution),
            'powerup_matrix_heatmap': powerup_matrix_data,
            'matching_matrix_heatmap': matching_matrix_data
        }
    
    def run_simulation(self, progress_callback=None):
        """Execute complete simulation workflow
        
        Args:
            progress_callback: Optional callback function(status, progress_pct) 
                              Returns True if cancellation requested
        """
        def update_progress(status, pct):
            print(status)
            if progress_callback:
                return progress_callback(status, pct)
            return False
        
        print("=" * 60)
        print("POWERUP BONUS SIMULATION")
        print("=" * 60)
        
        total_users = self.config.get('total_users', 10000)
        max_depth = self.config.get('max_depth', 7)
        
        if update_progress(f'Generating hierarchy ({total_users:,} users)...', 15):
            raise Exception('Cancelled by user')
        self.generate_hierarchy(total_users, max_depth)
        
        avg_units = self.config.get('avg_units', 8)
        min_units = self.config.get('min_units', 1)
        
        if update_progress('Assigning purchases...', 30):
            raise Exception('Cancelled by user')
        self.assign_purchases(avg_units, min_units)
        
        if update_progress('Calculating VP...', 45):
            raise Exception('Cancelled by user')
        self.calculate_vp()
        
        if update_progress('Calculating leg VP...', 55):
            raise Exception('Cancelled by user')
        self.calculate_leg_vp()
        
        if update_progress('Determining ranks...', 65):
            raise Exception('Cancelled by user')
        self.determine_ranks()
        
        if update_progress('Determining line qualifications...', 70):
            raise Exception('Cancelled by user')
        self.determine_line_qualification()
        
        if update_progress('Assigning PowerUp percentages...', 75):
            raise Exception('Cancelled by user')
        self.assign_powerup_percentages()
        
        if update_progress('Assigning Matching percentages...', 80):
            raise Exception('Cancelled by user')
        self.assign_matching_percentages()
        
        if update_progress('Calculating bonuses...', 85):
            raise Exception('Cancelled by user')
        self.calculate_bonuses()
        
        if update_progress('Generating statistics...', 90):
            raise Exception('Cancelled by user')
        stats = self.get_statistics()
        
        print("\n" + "=" * 60)
        print("SIMULATION COMPLETE")
        print("=" * 60)
        
        return stats


def create_default_config():
    """Create default configuration"""
    return {
        'total_users': 10000,
        'max_depth': 7,
        'avg_units': 8,
        'min_units': 1,
        'promotion_enabled': True,
        'promotion_target_units': 8,
        'promotion_intensity': 30,
        'use_hierarchy_cache': True,
        'force_regenerate_hierarchy': False,
        'rank_vp_requirements': {
            'N1': 5000, 'N2': 15000, 'N3': 30000, 'N4': 100000,
            'N5': 250000, 'N6': 500000, 'N7': 1000000
        },
        'line_thresholds': {2: 0.30, 3: 0.20, 4: 0.10, 5: 0.05},
        # PowerUp Matrix: 0 means not available for that rank/line combination
        'powerup_matrix': {
            'N1': {1: 0.03, 2: 0.05, 3: 0.00, 4: 0.00, 5: 0.00},  # Only 1-2 lines
            'N2': {1: 0.04, 2: 0.06, 3: 0.00, 4: 0.00, 5: 0.00},  # Only 1-2 lines
            'N3': {1: 0.05, 2: 0.08, 3: 0.10, 4: 0.00, 5: 0.00},  # Only 1-3 lines
            'N4': {1: 0.06, 2: 0.11, 3: 0.13, 4: 0.15, 5: 0.00},  # Only 1-4 lines
            'N5': {1: 0.07, 2: 0.12, 3: 0.14, 4: 0.17, 5: 0.19},  # All 5 lines
            'N6': {1: 0.08, 2: 0.13, 3: 0.16, 4: 0.19, 5: 0.21},  # All 5 lines
            'N7': {1: 0.09, 2: 0.14, 3: 0.18, 4: 0.21, 5: 0.23}   # All 5 lines
        },
        'matching_percentages': {
            'N1': 0.0, 'N2': 0.0, 'N3': 0.10, 'N4': 0.125,
            'N5': 0.15, 'N6': 0.20, 'N7': 0.25
        }
    }


if __name__ == "__main__":
    config = create_default_config()
    sim = MLMSimulation(config)
    stats = sim.run_simulation()
    
    print(f"\nTotal Users: {stats['total_users']:,}")
    print(f"Total Sales: ${stats['total_purchase_amount']:,.2f}")
    print(f"Total PowerUp: ${stats['total_powerup']:,.2f}")
    print(f"Total Matching: ${stats['total_matching']:,.2f}")
    print(f"Payout Ratio: {stats['payout_ratio']:.2f}%")
    
    print("\n" + "-" * 50)
    print("POWERUP DISTRIBUTION (sorted by amount)")
    print("-" * 50)
    for item in stats['powerup_distribution']:
        marker = "●" if item['in_top_80'] else "○"
        print(f"{marker} {item['percentage']:>5}: ${item['total_earned']:>12,.2f} ({item['pct_of_total_payout']:.1f}%) "
              f"- {item['user_count']} users - {item['rank_lines']}")