"""
Direct Bonus Simulation Engine
==============================

Simulates Direct Bonus payouts for NLK and USDN programs over 12 months.

KEY FEATURES:
- Time-based user join simulation (logistic growth curve)
- NLK Direct Bonus: 15% (first 30 days) / 10% (after 30 days)
- USDN Direct Bonus: L1=7%, L2=1.5%, L3=1.5% with 2500 USDN eligibility
- Reinvestment cascade tracking
- Monthly aggregation and metrics

RESEARCH-BACKED METHODOLOGY:
============================

CRITICAL DESIGN PRINCIPLE: NLK inflow in Direct Bonus should approximately 
match PowerUp simulation for the same user base, since both represent 
the same NLK program.

1. USER GROWTH MODEL - Logistic Growth Curve
   Formula: Users(month) = MaxUsers / (1 + e^(-k*(month - midpoint)))
   Based on Rogers' Diffusion of Innovations (1962)

2. PARTICIPATION & PURCHASE PATTERNS (FTC MLM Data)
   Source: FTC Economic Analysis of MLM (2018), DSA Industry Statistics
   
   Key findings from real MLM data:
   - 47-73% of participants make ANY purchase
   - Only 15-25% become "active" (repeat purchasers)
   - 85% become inactive within 12 months
   - Top 10% generate 60%+ of total volume
   - Median total participant spend: $200-$1000 lifetime
   
3. CHURN MODEL (Based on MLM retention studies)
   - Month 1: 100% potential activity
   - Month 3: 50% still potentially active
   - Month 6: 25% still potentially active  
   - Month 12: 10% still potentially active
   
4. AMOUNT DISTRIBUTION
   - Follows same mixture model as PowerUp for consistency
   - NLK and USDN are SEPARATE programs (not everyone does both)
   - USDN eligibility ($2500) is intentionally hard to reach

References:
- FTC MLM Income Disclosure Analysis (2018)
- Taylor, J.M. (2011). "The Case For and Against Multi-level Marketing"
- DSA Annual Reports 2015-2023
- Rogers, E.M. (1962). Diffusion of Innovations
"""

import random
import numpy as np
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import math
import time

# Set seeds for reproducibility
random.seed(42)
np.random.seed(42)


@dataclass
class DirectBonusUser:
    """Extended user data for Direct Bonus simulation"""
    user_id: int
    level: int
    sponsor_id: Optional[int]
    direct_referrals: List[int] = field(default_factory=list)
    
    # Temporal data
    join_month: int = 1
    join_day: int = 1
    
    # Program participation
    programs: List[str] = field(default_factory=list)  # ['NLK'], ['USDN'], or both
    
    # Activity status
    is_active: bool = True  # Becomes False after churn
    churn_month: int = 13   # Month they become inactive (13 = never churns)
    
    # Purchase behavior type
    buyer_type: str = ""  # 'power', 'regular', 'minimal', 'non_buyer'
    
    # Addition tracking
    nlk_additions: List[Dict] = field(default_factory=list)
    usdn_additions: List[Dict] = field(default_factory=list)
    cumulative_nlk_units: int = 0
    cumulative_usdn: float = 0.0
    is_usdn_eligible: bool = False
    
    # Behavioral flags
    has_added_nlk: bool = False
    has_added_usdn: bool = False
    nlk_purchase_count: int = 0
    usdn_purchase_count: int = 0
    
    # Earnings tracking
    direct_bonus_nlk_earned: float = 0.0
    direct_bonus_usdn_earned: float = 0.0
    usdn_w_received: float = 0.0
    usdn_received: float = 0.0
    
    # Disqualified tracking
    disqualified_amount: float = 0.0


class DirectBonusSimulation:
    """
    Direct Bonus Simulation for NLK and USDN programs.
    
    Integrates with existing hierarchy and adds time-based bonus calculations.
    """
    
    def __init__(self, config: Dict, hierarchy_users: Dict = None):
        """
        Initialize simulation.
        
        Args:
            config: Configuration dictionary
            hierarchy_users: Pre-loaded hierarchy from MLMSimulation (optional)
        """
        self.config = config
        self.users: Dict[int, DirectBonusUser] = {}
        self.monthly_data: Dict[int, Dict] = {}
        
        # Growth parameters
        self.target_users = config.get('target_users', 100000)
        self.growth_rate = config.get('growth_rate', 0.8)
        self.growth_midpoint = config.get('growth_midpoint', 4.5)
        
        # Program participation rates
        self.nlk_only_pct = config.get('nlk_only_pct', 0.40)
        self.usdn_only_pct = config.get('usdn_only_pct', 0.20)
        self.both_programs_pct = config.get('both_programs_pct', 0.40)
        
        # NLK Direct Bonus rates
        self.nlk_promo_days = config.get('nlk_promo_days', 30)
        self.nlk_promo_rate = config.get('nlk_promo_rate', 0.15)
        self.nlk_standard_rate = config.get('nlk_standard_rate', 0.10)
        self.nlk_avg_units = config.get('nlk_avg_units', 40)
        self.nlk_unit_price = config.get('nlk_unit_price', 25)
        
        # USDN Direct Bonus rates
        self.usdn_l1_rate = config.get('usdn_l1_rate', 0.07)
        self.usdn_l2_rate = config.get('usdn_l2_rate', 0.015)
        self.usdn_l3_rate = config.get('usdn_l3_rate', 0.015)
        self.usdn_eligibility_threshold = config.get('usdn_eligibility_threshold', 2500)
        self.usdn_avg_amount = config.get('usdn_avg_amount', 2000)
        
        # Distribution split
        self.usdn_w_pct = config.get('usdn_w_pct', 0.80)
        self.usdn_pct = config.get('usdn_pct', 0.20)
        
        # Reinvestment settings
        self.enable_reinvestment = config.get('enable_reinvestment', True)
        self.reinvestment_rate = config.get('reinvestment_rate', 0.50)
        self.reinvestment_program = config.get('reinvestment_program', 'random')  # 'nlk', 'usdn', 'random'
        self.cascade_stop_threshold = config.get('cascade_stop_threshold', 1.0)
        
        # Promotion months
        self.nlk_promo_months = config.get('nlk_promo_months', [3, 6, 9])
        self.usdn_promo_months = config.get('usdn_promo_months', [2, 5, 8, 11])
        self.promo_participation_boost = config.get('promo_participation_boost', 0.50)
        self.promo_amount_boost = config.get('promo_amount_boost', 0.30)
        
        # Behavioral patterns
        self.monthly_adders_pct = config.get('monthly_adders_pct', 0.30)
        self.quarterly_adders_pct = config.get('quarterly_adders_pct', 0.20)
        self.one_time_adders_pct = config.get('one_time_adders_pct', 0.50)
        
        # Load hierarchy if provided
        if hierarchy_users:
            self._import_hierarchy(hierarchy_users)
    
    def _import_hierarchy(self, hierarchy_users: Dict):
        """
        Import users from existing MLMSimulation hierarchy.
        Creates fresh DirectBonusUser objects to ensure clean state.
        """
        print(f"Importing hierarchy for Direct Bonus simulation...")
        
        self.users = {}
        for user_id, user in hierarchy_users.items():
            # Create fresh user with only hierarchy data (no simulation state)
            db_user = DirectBonusUser(
                user_id=user.user_id,
                level=user.level,
                sponsor_id=user.sponsor_id,
                direct_referrals=list(user.direct_referrals) if user.direct_referrals else []
            )
            self.users[user_id] = db_user
        
        # Update target_users to match actual hierarchy
        self.target_users = len(self.users)
        
        print(f"✓ Imported {len(self.users):,} users (fresh state)")
    
    def _logistic_growth(self, month: int) -> float:
        """
        Calculate cumulative users by month using logistic growth curve.
        
        Formula: Users(month) = MaxUsers / (1 + e^(-k*(month - midpoint)))
        
        This models realistic MLM growth:
        - Slow start (awareness building)
        - Rapid middle growth (viral expansion)
        - Plateau (market saturation)
        """
        return self.target_users / (1 + math.exp(-self.growth_rate * (month - self.growth_midpoint)))
    
    def assign_join_dates(self):
        """
        Assign join dates to users based on logistic growth curve.
        
        Each user is probabilistically assigned to a month based on the
        growth curve, then given a random day within that month.
        """
        print("\nAssigning join dates using logistic growth model...")
        
        total_users = len(self.users)
        
        # Calculate target users per month based on logistic curve
        monthly_targets = []
        prev_cumulative = 0
        for month in range(1, 13):
            cumulative = int(self._logistic_growth(month))
            new_this_month = cumulative - prev_cumulative
            monthly_targets.append(max(0, new_this_month))
            prev_cumulative = cumulative
        
        # Normalize to match actual user count
        total_target = sum(monthly_targets)
        if total_target > 0:
            monthly_targets = [int(m * total_users / total_target) for m in monthly_targets]
        
        # Adjust last month to account for rounding
        monthly_targets[11] += total_users - sum(monthly_targets)
        
        # Assign users to months
        user_ids = list(self.users.keys())
        random.shuffle(user_ids)
        
        user_index = 0
        month_user_counts = {}
        
        for month in range(1, 13):
            count = monthly_targets[month - 1]
            month_user_counts[month] = count
            
            for _ in range(count):
                if user_index >= len(user_ids):
                    break
                    
                user_id = user_ids[user_index]
                self.users[user_id].join_month = month
                self.users[user_id].join_day = random.randint(1, 28)  # Simplify to 28 days
                user_index += 1
        
        print("✓ Join dates assigned")
        print("  Monthly distribution:")
        for month in range(1, 13):
            pct = (month_user_counts[month] / total_users) * 100
            bar = "█" * int(pct / 2)
            print(f"    Month {month:2d}: {month_user_counts[month]:>6,} ({pct:>5.1f}%) {bar}")
    
    def assign_program_participation(self):
        """
        Assign program participation with level-based bias.
        
        Early joiners (higher levels) are more likely to participate in both programs,
        reflecting greater commitment and financial capability.
        
        RESEARCH-BACKED BUYER TYPE DISTRIBUTION (FTC MLM Data):
        - Non-buyers: 30% join but never purchase
        - One-time buyers: 45% make single purchase then inactive
        - Occasional buyers: 20% make 2-3 purchases over 12 months  
        - Active buyers: 5% regular purchasers
        
        This matches FTC finding that 85% become inactive within 12 months.
        """
        print("\nAssigning program participation and buyer types...")
        
        nlk_only = 0
        usdn_only = 0
        both = 0
        
        buyer_type_counts = {'non_buyer': 0, 'one_time': 0, 'occasional': 0, 'active': 0}
        
        for user in self.users.values():
            # Level-based adjustment (early joiners more committed)
            level_factor = max(0, 1 - (user.level - 1) / 30)  # Decreases with level
            
            # Assign BUYER TYPE first (independent of program)
            # RESEARCH-BACKED (FTC 2018, AARP):
            # - 47-73% make at least ONE purchase
            # - Top 10% generate 60%+ of volume
            # - 85% become inactive within 12 months
            # Target: ~25% non-buyers, 45% one-time, 22% occasional, 8% active
            type_roll = random.random()
            
            # Higher levels have slightly higher non-buyer rate
            non_buyer_threshold = 0.22 + (1 - level_factor) * 0.08  # 22-30% non-buyers
            one_time_threshold = non_buyer_threshold + 0.45  # 45% one-time
            occasional_threshold = one_time_threshold + 0.22  # 22% occasional
            # remainder ~8% active
            
            if type_roll < non_buyer_threshold:
                user.buyer_type = 'non_buyer'
                user.programs = []  # No programs
                buyer_type_counts['non_buyer'] += 1
            elif type_roll < one_time_threshold:
                user.buyer_type = 'one_time'
                buyer_type_counts['one_time'] += 1
            elif type_roll < occasional_threshold:
                user.buyer_type = 'occasional'
                buyer_type_counts['occasional'] += 1
            else:
                user.buyer_type = 'active'
                buyer_type_counts['active'] += 1
            
            # Assign PROGRAM participation (only for buyers)
            if user.buyer_type != 'non_buyer':
                # Adjusted probabilities based on level
                both_pct = self.both_programs_pct + (level_factor * 0.15)
                nlk_pct = self.nlk_only_pct - (level_factor * 0.05)
                usdn_pct = self.usdn_only_pct - (level_factor * 0.10)
                
                # Normalize
                total = both_pct + nlk_pct + usdn_pct
                both_pct /= total
                nlk_pct /= total
                
                roll = random.random()
                
                if roll < both_pct:
                    user.programs = ['NLK', 'USDN']
                    both += 1
                elif roll < both_pct + nlk_pct:
                    user.programs = ['NLK']
                    nlk_only += 1
                else:
                    user.programs = ['USDN']
                    usdn_only += 1
            
            # Assign churn month (when user becomes inactive)
            # Research: 50% inactive by month 3, 75% by month 6, 90% by month 12
            if user.buyer_type == 'non_buyer':
                user.churn_month = user.join_month  # Immediately inactive
            elif user.buyer_type == 'one_time':
                # Churn 1-2 months after joining
                user.churn_month = user.join_month + random.randint(1, 2)
            elif user.buyer_type == 'occasional':
                # Churn 3-6 months after joining
                user.churn_month = user.join_month + random.randint(3, 6)
            else:  # active
                # Stay active longer, some through month 12
                user.churn_month = min(13, user.join_month + random.randint(6, 12))
        
        total = len(self.users)
        print(f"✓ Buyer type distribution:")
        print(f"    Non-buyers:  {buyer_type_counts['non_buyer']:>6,} ({buyer_type_counts['non_buyer']/total*100:.1f}%)")
        print(f"    One-time:    {buyer_type_counts['one_time']:>6,} ({buyer_type_counts['one_time']/total*100:.1f}%)")
        print(f"    Occasional:  {buyer_type_counts['occasional']:>6,} ({buyer_type_counts['occasional']/total*100:.1f}%)")
        print(f"    Active:      {buyer_type_counts['active']:>6,} ({buyer_type_counts['active']/total*100:.1f}%)")
        
        buyers_total = nlk_only + usdn_only + both
        print(f"✓ Program participation (among buyers):")
        print(f"    NLK Only:  {nlk_only:>6,} ({nlk_only/max(1,buyers_total)*100:.1f}%)")
        print(f"    USDN Only: {usdn_only:>6,} ({usdn_only/max(1,buyers_total)*100:.1f}%)")
        print(f"    Both:      {both:>6,} ({both/max(1,buyers_total)*100:.1f}%)")
    
    def _should_user_add_this_month(self, user: DirectBonusUser, month: int, program: str) -> bool:
        """
        Determine if a user should make an addition this month.
        
        RESEARCH-BACKED MODEL:
        - Respects buyer type (non_buyer, one_time, occasional, active)
        - Implements churn (users become inactive over time)
        - First purchase probability varies by buyer type
        - Repeat purchase probability is LOW (matches FTC data)
        """
        
        # Can't add before joining
        if month < user.join_month:
            return False
        
        # Check if user has churned
        if month >= user.churn_month:
            return False
        
        # Non-buyers never purchase
        if user.buyer_type == 'non_buyer':
            return False
        
        # Check if program is enabled for user
        if program not in user.programs:
            return False
        
        months_since_join = month - user.join_month
        is_promo_month = (
            (program == 'NLK' and month in self.nlk_promo_months) or
            (program == 'USDN' and month in self.usdn_promo_months)
        )
        
        # FIRST PURCHASE LOGIC
        if program == 'NLK' and not user.has_added_nlk:
            if months_since_join == 0:
                # First month - buyers WILL buy (that's why they're buyers)
                # Research: 80-90% of "buyers" complete first purchase within 30 days
                base_prob = {
                    'one_time': 0.88,    # Very high - this IS their purchase
                    'occasional': 0.75,  # High
                    'active': 0.82       # Very high
                }.get(user.buyer_type, 0.60)
                
                if is_promo_month:
                    base_prob = min(0.95, base_prob * 1.05)
                
                return random.random() < base_prob
            else:
                # Later months - declining probability for first purchase
                decay = 0.55 ** months_since_join
                prob = 0.25 * decay
                if is_promo_month:
                    prob *= 1.15
                return random.random() < prob
        
        if program == 'USDN' and not user.has_added_usdn:
            if months_since_join == 0:
                # USDN first purchase - still lower than NLK
                base_prob = {
                    'one_time': 0.50,
                    'occasional': 0.40,
                    'active': 0.55
                }.get(user.buyer_type, 0.30)
                
                if is_promo_month:
                    base_prob = min(0.65, base_prob * 1.08)
                
                return random.random() < base_prob
            else:
                decay = 0.45 ** months_since_join
                prob = 0.18 * decay
                if is_promo_month:
                    prob *= 1.15
                return random.random() < prob
        
        # REPEAT PURCHASE LOGIC (only for users who already purchased)
        if program == 'NLK' and user.has_added_nlk:
            if user.buyer_type == 'one_time':
                return False  # One-time buyers don't repeat
            
            if user.buyer_type == 'occasional':
                # 2-3 purchases total, so ~10-15% chance per month after first
                if user.nlk_purchase_count >= 3:
                    return False  # Cap at 3 purchases
                prob = 0.08 if not is_promo_month else 0.12
                return random.random() < prob
            
            if user.buyer_type == 'active':
                # More regular but not every month
                prob = 0.20 if not is_promo_month else 0.30
                return random.random() < prob
        
        if program == 'USDN' and user.has_added_usdn:
            if user.buyer_type == 'one_time':
                return False
            
            if user.buyer_type == 'occasional':
                if user.usdn_purchase_count >= 2:
                    return False
                prob = 0.05 if not is_promo_month else 0.08
                return random.random() < prob
            
            if user.buyer_type == 'active':
                prob = 0.12 if not is_promo_month else 0.18
                return random.random() < prob
        
        return False
    
    def _generate_nlk_amount(self, user: DirectBonusUser, month: int) -> int:
        """
        Generate NLK addition amount.
        
        CONSISTENT WITH POWERUP:
        PowerUp uses a mixture model that produces ~$400-1200 per user.
        Direct Bonus should match this distribution for NLK purchases.
        
        MIXTURE MODEL:
        - 15% minimum buyers: 1-5 units ($25-125)
        - 55% moderate buyers: 6-30 units ($150-750)
        - 25% above-average: 31-80 units ($775-2000)
        - 5% power buyers: 81-160 units ($2025-4000)
        """
        is_promo = month in self.nlk_promo_months
        
        roll = random.random()
        
        if user.buyer_type == 'active':
            # Active buyers purchase larger amounts
            if roll < 0.08:
                units = random.randint(1, 5)
            elif roll < 0.40:
                units = random.randint(10, 40)
            elif roll < 0.80:
                units = random.randint(41, 100)
            else:
                units = random.randint(101, 180)
        elif user.buyer_type == 'occasional':
            # Occasional buyers are moderate
            if roll < 0.12:
                units = random.randint(1, 5)
            elif roll < 0.60:
                units = random.randint(6, 30)
            elif roll < 0.92:
                units = random.randint(31, 70)
            else:
                units = random.randint(71, 120)
        else:  # one_time or default
            # One-time buyers match PowerUp overall distribution
            if roll < 0.15:
                units = random.randint(1, 5)
            elif roll < 0.70:
                units = random.randint(6, 30)
            elif roll < 0.95:
                units = random.randint(31, 80)
            else:
                units = random.randint(81, 160)
        
        # Small promo boost
        if is_promo:
            units = int(units * 1.08)
        
        return max(1, min(units, 200))
    
    def _generate_usdn_amount(self, user: DirectBonusUser, month: int) -> float:
        """
        Generate USDN addition amount - REALISTIC with lower amounts.
        
        RESEARCH-BACKED:
        - USDN is "investment" tier, most participants cautious
        - Average: $200-600 per addition
        - Very few reach $2500 eligibility threshold
        - Requires multiple additions over time
        
        DISTRIBUTION:
        - 40% small: $50-300
        - 35% medium: $300-800
        - 20% larger: $800-1500
        - 5% significant: $1500-3000
        """
        is_promo = month in self.usdn_promo_months
        
        roll = random.random()
        
        if user.buyer_type == 'active':
            # Active USDN buyers invest more but still conservative
            if roll < 0.25:
                amount = random.uniform(100, 400)
            elif roll < 0.55:
                amount = random.uniform(400, 1000)
            elif roll < 0.85:
                amount = random.uniform(1000, 2000)
            else:
                amount = random.uniform(2000, 4000)  # Rare larger deposits
        elif user.buyer_type == 'occasional':
            if roll < 0.35:
                amount = random.uniform(50, 300)
            elif roll < 0.75:
                amount = random.uniform(300, 700)
            else:
                amount = random.uniform(700, 1500)
        else:  # one_time
            # Most one-time USDN adds are small
            if roll < 0.50:
                amount = random.uniform(50, 250)
            elif roll < 0.85:
                amount = random.uniform(250, 600)
            else:
                amount = random.uniform(600, 1200)
        
        if is_promo:
            amount *= 1.08  # Small boost
        
        return round(max(50, min(amount, 5000)), 2)  # Min $50, Max $5K
    
    def _get_upline_chain(self, user_id: int, max_levels: int = 3) -> List[int]:
        """Get upline chain up to max_levels"""
        chain = []
        current_id = self.users[user_id].sponsor_id
        
        while current_id is not None and len(chain) < max_levels:
            chain.append(current_id)
            current_id = self.users[current_id].sponsor_id
        
        return chain
    
    def _calculate_nlk_direct_bonus(self, user_id: int, units: int, month: int, day: int) -> Dict:
        """
        Calculate NLK Direct Bonus for a single addition.
        
        Returns dict with bonus details.
        """
        user = self.users[user_id]
        amount = units * self.nlk_unit_price
        
        # Determine rate based on days since user joined
        user_join_day_of_year = (user.join_month - 1) * 30 + user.join_day
        addition_day_of_year = (month - 1) * 30 + day
        days_since_join = addition_day_of_year - user_join_day_of_year
        
        if days_since_join <= self.nlk_promo_days:
            rate = self.nlk_promo_rate
            rate_type = 'promo'
        else:
            rate = self.nlk_standard_rate
            rate_type = 'standard'
        
        bonus_amount = amount * rate
        
        # Find sponsor (L1 upline)
        if user.sponsor_id is None:
            return {
                'paid': False,
                'reason': 'No sponsor',
                'amount': 0,
                'rate': rate,
                'rate_type': rate_type
            }
        
        sponsor = self.users[user.sponsor_id]
        
        # Credit sponsor
        usdn_w = bonus_amount * self.usdn_w_pct
        usdn = bonus_amount * self.usdn_pct
        
        sponsor.direct_bonus_nlk_earned += bonus_amount
        sponsor.usdn_w_received += usdn_w
        sponsor.usdn_received += usdn
        
        return {
            'paid': True,
            'sponsor_id': user.sponsor_id,
            'amount': bonus_amount,
            'usdn_w': usdn_w,
            'usdn': usdn,
            'rate': rate,
            'rate_type': rate_type
        }
    
    def _calculate_usdn_direct_bonus(self, user_id: int, amount: float, month: int) -> Dict:
        """
        Calculate USDN Direct Bonus for a single addition.
        
        L1: 7%, L2: 1.5%, L3: 1.5% (only if eligible)
        """
        results = {
            'l1': {'paid': False, 'amount': 0, 'disqualified': 0},
            'l2': {'paid': False, 'amount': 0, 'disqualified': 0},
            'l3': {'paid': False, 'amount': 0, 'disqualified': 0},
            'total_paid': 0,
            'total_disqualified': 0
        }
        
        upline_chain = self._get_upline_chain(user_id, max_levels=3)
        rates = [self.usdn_l1_rate, self.usdn_l2_rate, self.usdn_l3_rate]
        level_keys = ['l1', 'l2', 'l3']
        
        for i, (upline_id, rate, level_key) in enumerate(zip(upline_chain, rates, level_keys)):
            bonus_amount = amount * rate
            upline = self.users[upline_id]
            
            if upline.is_usdn_eligible:
                # Eligible - pay bonus
                usdn_w = bonus_amount * self.usdn_w_pct
                usdn = bonus_amount * self.usdn_pct
                
                upline.direct_bonus_usdn_earned += bonus_amount
                upline.usdn_w_received += usdn_w
                upline.usdn_received += usdn
                
                results[level_key] = {
                    'paid': True,
                    'upline_id': upline_id,
                    'amount': bonus_amount,
                    'usdn_w': usdn_w,
                    'usdn': usdn
                }
                results['total_paid'] += bonus_amount
            else:
                # Not eligible - track disqualified
                upline.disqualified_amount += bonus_amount
                results[level_key] = {
                    'paid': False,
                    'upline_id': upline_id,
                    'amount': 0,
                    'disqualified': bonus_amount,
                    'reason': f'Below {self.usdn_eligibility_threshold} USDN threshold'
                }
                results['total_disqualified'] += bonus_amount
        
        # Handle missing uplines
        for i in range(len(upline_chain), 3):
            level_key = level_keys[i]
            results[level_key] = {
                'paid': False,
                'amount': 0,
                'disqualified': 0,
                'reason': f'No upline at level {i+1}'
            }
        
        return results
    
    def _process_reinvestment_cascade(self, month: int) -> Dict:
        """
        Process reinvestment cascade for the month.
        
        Users reinvest a portion of their USDN component into chosen program.
        """
        if not self.enable_reinvestment:
            return {'generations': 0, 'total_reinvested': 0, 'cascade_bonus': 0}
        
        total_reinvested = 0
        total_cascade_bonus = 0
        generation = 0
        max_generations = 0
        
        # Collect users with USDN to reinvest
        reinvest_queue = []
        for user in self.users.values():
            reinvest_amount = user.usdn_received * self.reinvestment_rate
            if reinvest_amount >= self.cascade_stop_threshold:
                reinvest_queue.append((user.user_id, reinvest_amount))
                user.usdn_received -= reinvest_amount  # Deduct reinvested amount
        
        while reinvest_queue and generation < 20:  # Cap at 20 generations for safety
            generation += 1
            next_queue = []
            
            for user_id, amount in reinvest_queue:
                # Determine program to reinvest into
                if self.reinvestment_program == 'nlk':
                    program = 'NLK'
                elif self.reinvestment_program == 'usdn':
                    program = 'USDN'
                else:  # random
                    program = random.choice(['NLK', 'USDN'])
                
                total_reinvested += amount
                
                if program == 'NLK':
                    # Reinvest as NLK units
                    units = max(1, int(amount / self.nlk_unit_price))
                    bonus_result = self._calculate_nlk_direct_bonus(user_id, units, month, 15)
                    if bonus_result['paid']:
                        total_cascade_bonus += bonus_result['amount']
                        
                        # Queue sponsor's USDN component for next cascade
                        sponsor = self.users[bonus_result['sponsor_id']]
                        next_amount = bonus_result['usdn'] * self.reinvestment_rate
                        if next_amount >= self.cascade_stop_threshold:
                            next_queue.append((bonus_result['sponsor_id'], next_amount))
                            sponsor.usdn_received -= next_amount
                
                else:  # USDN
                    # Update user's cumulative USDN
                    user = self.users[user_id]
                    user.cumulative_usdn += amount
                    if user.cumulative_usdn >= self.usdn_eligibility_threshold:
                        user.is_usdn_eligible = True
                    
                    bonus_result = self._calculate_usdn_direct_bonus(user_id, amount, month)
                    total_cascade_bonus += bonus_result['total_paid']
                    
                    # Queue uplines' USDN components for next cascade
                    for level_key in ['l1', 'l2', 'l3']:
                        level_result = bonus_result[level_key]
                        if level_result['paid'] and 'upline_id' in level_result:
                            upline = self.users[level_result['upline_id']]
                            next_amount = level_result['usdn'] * self.reinvestment_rate
                            if next_amount >= self.cascade_stop_threshold:
                                next_queue.append((level_result['upline_id'], next_amount))
                                upline.usdn_received -= next_amount
            
            reinvest_queue = next_queue
            if reinvest_queue:
                max_generations = generation
        
        return {
            'generations': max_generations,
            'total_reinvested': total_reinvested,
            'cascade_bonus': total_cascade_bonus
        }
    
    def simulate_month(self, month: int) -> Dict:
        """Simulate a single month's additions and bonuses"""
        
        month_data = {
            'month': month,
            'new_users': 0,
            'active_users': 0,
            'inflow': {
                'nlk_units': 0,
                'nlk_dollars': 0,
                'usdn_dollars': 0,
                'total': 0
            },
            'direct_bonus': {
                'nlk_paid': 0,
                'nlk_promo_paid': 0,
                'nlk_standard_paid': 0,
                'usdn_l1_paid': 0,
                'usdn_l2_paid': 0,
                'usdn_l3_paid': 0,
                'usdn_total_paid': 0,
                'usdn_disqualified': 0,
                'total_paid': 0
            },
            'cascade': {
                'generations': 0,
                'reinvested': 0,
                'bonus': 0
            },
            'distribution': {
                'usdn_w_distributed': 0,
                'usdn_distributed': 0
            },
            # Payout percentages (for display)
            'payout_pct': {
                'nlk': 0,
                'usdn_l1': 0,
                'usdn_l2': 0,
                'usdn_l3': 0,
                'usdn_disq': 0
            }
        }
        
        # Count new users this month
        for user in self.users.values():
            if user.join_month == month:
                month_data['new_users'] += 1
        
        # Process NLK additions
        for user_id, user in self.users.items():
            if self._should_user_add_this_month(user, month, 'NLK'):
                units = self._generate_nlk_amount(user, month)
                day = random.randint(1, 28)
                
                # Record addition
                user.nlk_additions.append({
                    'month': month,
                    'day': day,
                    'units': units,
                    'amount': units * self.nlk_unit_price
                })
                user.cumulative_nlk_units += units
                user.has_added_nlk = True
                user.nlk_purchase_count += 1
                
                month_data['inflow']['nlk_units'] += units
                month_data['inflow']['nlk_dollars'] += units * self.nlk_unit_price
                month_data['active_users'] += 1
                
                # Calculate direct bonus
                bonus_result = self._calculate_nlk_direct_bonus(user_id, units, month, day)
                if bonus_result['paid']:
                    month_data['direct_bonus']['nlk_paid'] += bonus_result['amount']
                    if bonus_result['rate_type'] == 'promo':
                        month_data['direct_bonus']['nlk_promo_paid'] += bonus_result['amount']
                    else:
                        month_data['direct_bonus']['nlk_standard_paid'] += bonus_result['amount']
                    month_data['distribution']['usdn_w_distributed'] += bonus_result['usdn_w']
                    month_data['distribution']['usdn_distributed'] += bonus_result['usdn']
        
        # Process USDN additions
        for user_id, user in self.users.items():
            if self._should_user_add_this_month(user, month, 'USDN'):
                amount = self._generate_usdn_amount(user, month)
                day = random.randint(1, 28)
                
                # Record addition
                user.usdn_additions.append({
                    'month': month,
                    'day': day,
                    'amount': amount
                })
                user.cumulative_usdn += amount
                user.has_added_usdn = True
                user.usdn_purchase_count += 1
                
                # Update eligibility
                if user.cumulative_usdn >= self.usdn_eligibility_threshold:
                    user.is_usdn_eligible = True
                
                month_data['inflow']['usdn_dollars'] += amount
                
                # Calculate direct bonus
                bonus_result = self._calculate_usdn_direct_bonus(user_id, amount, month)
                month_data['direct_bonus']['usdn_l1_paid'] += bonus_result['l1'].get('amount', 0)
                month_data['direct_bonus']['usdn_l2_paid'] += bonus_result['l2'].get('amount', 0)
                month_data['direct_bonus']['usdn_l3_paid'] += bonus_result['l3'].get('amount', 0)
                month_data['direct_bonus']['usdn_total_paid'] += bonus_result['total_paid']
                month_data['direct_bonus']['usdn_disqualified'] += bonus_result['total_disqualified']
                
                # Track distributions
                for level_key in ['l1', 'l2', 'l3']:
                    if bonus_result[level_key]['paid']:
                        month_data['distribution']['usdn_w_distributed'] += bonus_result[level_key].get('usdn_w', 0)
                        month_data['distribution']['usdn_distributed'] += bonus_result[level_key].get('usdn', 0)
        
        month_data['inflow']['total'] = month_data['inflow']['nlk_dollars'] + month_data['inflow']['usdn_dollars']
        
        # Process reinvestment cascade
        cascade_result = self._process_reinvestment_cascade(month)
        month_data['cascade']['generations'] = cascade_result['generations']
        month_data['cascade']['reinvested'] = cascade_result['total_reinvested']
        month_data['cascade']['bonus'] = cascade_result['cascade_bonus']
        
        # Total direct bonus paid
        month_data['direct_bonus']['total_paid'] = (
            month_data['direct_bonus']['nlk_paid'] +
            month_data['direct_bonus']['usdn_total_paid'] +
            month_data['cascade']['bonus']
        )
        
        # Calculate payout percentages
        nlk_in = month_data['inflow']['nlk_dollars']
        usdn_in = month_data['inflow']['usdn_dollars']
        
        if nlk_in > 0:
            month_data['payout_pct']['nlk'] = (month_data['direct_bonus']['nlk_paid'] / nlk_in) * 100
        
        if usdn_in > 0:
            month_data['payout_pct']['usdn_l1'] = (month_data['direct_bonus']['usdn_l1_paid'] / usdn_in) * 100
            month_data['payout_pct']['usdn_l2'] = (month_data['direct_bonus']['usdn_l2_paid'] / usdn_in) * 100
            month_data['payout_pct']['usdn_l3'] = (month_data['direct_bonus']['usdn_l3_paid'] / usdn_in) * 100
            month_data['payout_pct']['usdn_disq'] = (month_data['direct_bonus']['usdn_disqualified'] / usdn_in) * 100
        
        return month_data
    
    def run_simulation(self) -> Dict:
        """Run full 12-month simulation"""
        print("\n" + "=" * 60)
        print("DIRECT BONUS SIMULATION - STARTING")
        print("=" * 60)
        
        start_time = time.time()
        
        # Phase 1: Assign join dates
        self.assign_join_dates()
        
        # Phase 2: Assign program participation
        self.assign_program_participation()
        
        # Phase 3: Simulate each month
        print("\nSimulating 12 months...")
        for month in range(1, 13):
            self.monthly_data[month] = self.simulate_month(month)
            
            # Progress output
            m = self.monthly_data[month]
            print(f"  Month {month:2d}: Users +{m['new_users']:>6,} | "
                  f"Inflow ${m['inflow']['total']:>12,.0f} | "
                  f"Bonus ${m['direct_bonus']['total_paid']:>10,.0f}")
        
        # Phase 4: Generate summary statistics
        stats = self._generate_statistics()
        
        elapsed = time.time() - start_time
        print(f"\n✓ Simulation complete in {elapsed:.2f}s")
        print("=" * 60)
        
        return stats
    
    def _generate_statistics(self) -> Dict:
        """Generate comprehensive statistics"""
        
        # Aggregate monthly data
        total_inflow = sum(m['inflow']['total'] for m in self.monthly_data.values())
        total_nlk_inflow = sum(m['inflow']['nlk_dollars'] for m in self.monthly_data.values())
        total_usdn_inflow = sum(m['inflow']['usdn_dollars'] for m in self.monthly_data.values())
        total_nlk_units = sum(m['inflow']['nlk_units'] for m in self.monthly_data.values())
        
        total_nlk_bonus = sum(m['direct_bonus']['nlk_paid'] for m in self.monthly_data.values())
        total_usdn_bonus = sum(m['direct_bonus']['usdn_total_paid'] for m in self.monthly_data.values())
        total_disqualified = sum(m['direct_bonus']['usdn_disqualified'] for m in self.monthly_data.values())
        total_cascade_bonus = sum(m['cascade']['bonus'] for m in self.monthly_data.values())
        total_bonus = sum(m['direct_bonus']['total_paid'] for m in self.monthly_data.values())
        
        max_cascade_depth = max(m['cascade']['generations'] for m in self.monthly_data.values())
        avg_cascade_depth = np.mean([m['cascade']['generations'] for m in self.monthly_data.values()])
        
        # Top earners
        top_earners = sorted(
            self.users.values(),
            key=lambda u: u.direct_bonus_nlk_earned + u.direct_bonus_usdn_earned,
            reverse=True
        )[:20]
        
        # USDN eligibility stats
        eligible_users = sum(1 for u in self.users.values() if u.is_usdn_eligible)
        
        # Monthly breakdown for chart
        monthly_breakdown = []
        cumulative_users = 0
        for month in range(1, 13):
            m = self.monthly_data[month]
            cumulative_users += m['new_users']
            
            total_payout_ratio = (m['direct_bonus']['total_paid'] / m['inflow']['total'] * 100) if m['inflow']['total'] > 0 else 0
            
            monthly_breakdown.append({
                'month': month,
                'new_users': m['new_users'],
                'cumulative_users': cumulative_users,
                'inflow': m['inflow']['total'],
                'nlk_inflow': m['inflow']['nlk_dollars'],
                'usdn_inflow': m['inflow']['usdn_dollars'],
                'nlk_bonus': m['direct_bonus']['nlk_paid'],
                'usdn_bonus': m['direct_bonus']['usdn_total_paid'],
                'usdn_l1': m['direct_bonus']['usdn_l1_paid'],
                'usdn_l2': m['direct_bonus']['usdn_l2_paid'],
                'usdn_l3': m['direct_bonus']['usdn_l3_paid'],
                'cascade_bonus': m['cascade']['bonus'],
                'total_bonus': m['direct_bonus']['total_paid'],
                'disqualified': m['direct_bonus']['usdn_disqualified'],
                'payout_ratio': total_payout_ratio,
                'cascade_depth': m['cascade']['generations'],
                # Payout percentages by program
                'nlk_payout_pct': m['payout_pct']['nlk'],
                'usdn_l1_pct': m['payout_pct']['usdn_l1'],
                'usdn_l2_pct': m['payout_pct']['usdn_l2'],
                'usdn_l3_pct': m['payout_pct']['usdn_l3'],
                'usdn_disq_pct': m['payout_pct']['usdn_disq']
            })
        
        # Calculate overall payout ratios by program
        nlk_payout_ratio = (total_nlk_bonus / total_nlk_inflow * 100) if total_nlk_inflow > 0 else 0
        usdn_payout_ratio = (total_usdn_bonus / total_usdn_inflow * 100) if total_usdn_inflow > 0 else 0
        
        return {
            'summary': {
                'total_users': len(self.users),
                'total_inflow': total_inflow,
                'nlk_inflow': total_nlk_inflow,
                'usdn_inflow': total_usdn_inflow,
                'nlk_units': total_nlk_units,
                'total_bonus': total_bonus,
                'nlk_bonus': total_nlk_bonus,
                'usdn_bonus': total_usdn_bonus,
                'cascade_bonus': total_cascade_bonus,
                'disqualified': total_disqualified,
                'payout_ratio': (total_bonus / total_inflow * 100) if total_inflow > 0 else 0,
                'nlk_payout_ratio': nlk_payout_ratio,
                'usdn_payout_ratio': usdn_payout_ratio,
                'max_cascade_depth': max_cascade_depth,
                'avg_cascade_depth': avg_cascade_depth,
                'usdn_eligible_users': eligible_users,
                'usdn_eligible_pct': (eligible_users / len(self.users) * 100) if self.users else 0
            },
            'monthly': monthly_breakdown,
            'top_earners': [
                {
                    'user_id': u.user_id,
                    'level': u.level,
                    'join_month': u.join_month,
                    'nlk_bonus': u.direct_bonus_nlk_earned,
                    'usdn_bonus': u.direct_bonus_usdn_earned,
                    'total_bonus': u.direct_bonus_nlk_earned + u.direct_bonus_usdn_earned,
                    'usdn_w_received': u.usdn_w_received,
                    'is_usdn_eligible': u.is_usdn_eligible
                }
                for u in top_earners
            ],
            'config': {
                'nlk_promo_rate': self.nlk_promo_rate * 100,
                'nlk_standard_rate': self.nlk_standard_rate * 100,
                'usdn_l1_rate': self.usdn_l1_rate * 100,
                'usdn_l2_rate': self.usdn_l2_rate * 100,
                'usdn_l3_rate': self.usdn_l3_rate * 100,
                'usdn_eligibility_threshold': self.usdn_eligibility_threshold,
                'reinvestment_rate': self.reinvestment_rate * 100,
                'reinvestment_enabled': self.enable_reinvestment
            }
        }


def create_direct_bonus_config():
    """Create default configuration for Direct Bonus simulation"""
    return {
        # Hierarchy (will use existing or generate)
        'hierarchy_total_users': 10000,
        'hierarchy_max_depth': 7,
        'use_hierarchy_cache': True,
        'target_users': 10000,
        'growth_rate': 0.8,
        'growth_midpoint': 4.5,
        
        # Program participation
        'nlk_only_pct': 0.40,
        'usdn_only_pct': 0.20,
        'both_programs_pct': 0.40,
        
        # NLK Direct Bonus
        'nlk_promo_days': 30,
        'nlk_promo_rate': 0.15,
        'nlk_standard_rate': 0.10,
        'nlk_avg_units': 8,
        'nlk_unit_price': 25,
        
        # USDN Direct Bonus
        'usdn_l1_rate': 0.07,
        'usdn_l2_rate': 0.015,
        'usdn_l3_rate': 0.015,
        'usdn_eligibility_threshold': 2500,
        'usdn_avg_amount': 500,
        
        # Distribution split
        'usdn_w_pct': 0.80,
        'usdn_pct': 0.20,
        
        # Reinvestment (Cascade)
        'enable_reinvestment': True,
        'reinvestment_rate': 1.00,  # 100% reinvestment
        'reinvestment_program': 'random',  # 'nlk', 'usdn', 'random'
        'cascade_stop_threshold': 1.0,
        
        # Promotions - early months for growth push
        'nlk_promo_months': [1, 2],
        'usdn_promo_months': [2, 3, 4],
        'promo_participation_boost': 0.50,
        'promo_amount_boost': 0.30,
        
        # Behavioral patterns
        'monthly_adders_pct': 0.30,
        'quarterly_adders_pct': 0.20,
        'one_time_adders_pct': 0.50
    }


if __name__ == "__main__":
    # Test run
    config = create_direct_bonus_config()
    config['target_users'] = 1000  # Small test
    
    sim = DirectBonusSimulation(config)
    
    # Create simple test hierarchy
    from mlm_simulation import MLMSimulation, create_default_config
    mlm_config = create_default_config()
    mlm_config['total_users'] = 1000
    mlm_config['max_depth'] = 10
    mlm_config['use_hierarchy_cache'] = True
    
    mlm_sim = MLMSimulation(mlm_config)
    mlm_sim.generate_hierarchy(1000, 10)
    
    # Import hierarchy
    sim._import_hierarchy(mlm_sim.users)
    
    # Run simulation
    stats = sim.run_simulation()
    
    print("\n" + "=" * 60)
    print("SIMULATION SUMMARY")
    print("=" * 60)
    print(f"Total Users: {stats['summary']['total_users']:,}")
    print(f"Total Inflow: ${stats['summary']['total_inflow']:,.2f}")
    print(f"  - NLK: ${stats['summary']['nlk_inflow']:,.2f}")
    print(f"  - USDN: ${stats['summary']['usdn_inflow']:,.2f}")
    print(f"\nTotal Direct Bonus: ${stats['summary']['total_bonus']:,.2f}")
    print(f"  - NLK Bonus: ${stats['summary']['nlk_bonus']:,.2f}")
    print(f"  - USDN Bonus: ${stats['summary']['usdn_bonus']:,.2f}")
    print(f"  - Cascade Bonus: ${stats['summary']['cascade_bonus']:,.2f}")
    print(f"\nDisqualified (not paid): ${stats['summary']['disqualified']:,.2f}")
    print(f"Payout Ratio: {stats['summary']['payout_ratio']:.2f}%")
    print(f"Max Cascade Depth: {stats['summary']['max_cascade_depth']}")