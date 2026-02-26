"""
Validation Test Suite for MLM Simulation
Tests core calculations with known inputs and expected outputs
"""

from mlm_simulation import MLMSimulation, User
from collections import defaultdict


def test_vp_calculation():
    """Test VP flows correctly upward"""
    print("=" * 60)
    print("TEST 1: VP Calculation")
    print("=" * 60)
    
    # Create simple hierarchy manually
    sim = MLMSimulation({'total_users': 5, 'max_depth': 5})
    
    # Manual setup: Root -> A -> B -> C
    # C purchases $1000, should give 1000 VP to B, A, Root
    root = User(user_id=1, level=1, sponsor_id=None)
    user_a = User(user_id=2, level=2, sponsor_id=1)
    user_b = User(user_id=3, level=3, sponsor_id=2)
    user_c = User(user_id=4, level=4, sponsor_id=3)
    
    root.direct_referrals = [2]
    user_a.direct_referrals = [3]
    user_b.direct_referrals = [4]
    
    sim.users = {1: root, 2: user_a, 3: user_b, 4: user_c}
    
    # Set purchases
    user_c.purchase_amount = 1000
    
    # Calculate VP
    sim.calculate_vp()
    
    print(f"User C (purchaser) VP: {user_c.total_vp} (expected: 0)")
    print(f"User B VP: {user_b.total_vp} (expected: 1000)")
    print(f"User A VP: {user_a.total_vp} (expected: 1000)")
    print(f"Root VP: {root.total_vp} (expected: 1000)")
    
    # Validate
    assert user_c.total_vp == 0, "Purchaser should not get VP for own purchase"
    assert user_b.total_vp == 1000, "Direct sponsor should get 1000 VP"
    assert user_a.total_vp == 1000, "All uplines should get 1000 VP"
    assert root.total_vp == 1000, "Root should get 1000 VP"
    
    print("✓ VP Calculation PASSED\n")


def test_leg_vp_calculation():
    """Test leg VP includes entire downline"""
    print("=" * 60)
    print("TEST 2: Leg VP Calculation")
    print("=" * 60)
    
    sim = MLMSimulation({'total_users': 10, 'max_depth': 5})
    
    # Setup: Root has 2 direct referrals (A, B)
    # A has downline that purchased $5000 total
    # B has downline that purchased $3000 total
    root = User(user_id=1, level=1, sponsor_id=None)
    user_a = User(user_id=2, level=2, sponsor_id=1, purchase_amount=1000)
    user_a1 = User(user_id=3, level=3, sponsor_id=2, purchase_amount=2000)
    user_a2 = User(user_id=4, level=3, sponsor_id=2, purchase_amount=2000)
    user_b = User(user_id=5, level=2, sponsor_id=1, purchase_amount=1500)
    user_b1 = User(user_id=6, level=3, sponsor_id=5, purchase_amount=1500)
    
    root.direct_referrals = [2, 5]
    user_a.direct_referrals = [3, 4]
    user_b.direct_referrals = [6]
    
    sim.users = {1: root, 2: user_a, 3: user_a1, 4: user_a2, 5: user_b, 6: user_b1}
    
    # Calculate leg VP
    sim.calculate_leg_vp()
    
    # Leg A should have: A's purchase (1000) + A1 (2000) + A2 (2000) = 5000
    # Leg B should have: B's purchase (1500) + B1 (1500) = 3000
    
    print(f"Root has {len(root.leg_vps)} legs")
    print(f"Leg A VP: {root.leg_vps[0]} (expected: 5000)")
    print(f"Leg B VP: {root.leg_vps[1]} (expected: 3000)")
    
    assert len(root.leg_vps) == 2, "Root should have 2 legs"
    assert 5000 in root.leg_vps, "Leg A should total 5000"
    assert 3000 in root.leg_vps, "Leg B should total 3000"
    
    print("✓ Leg VP Calculation PASSED\n")


def test_line_qualification():
    """Test line qualification logic with combining"""
    print("=" * 60)
    print("TEST 3: Line Qualification")
    print("=" * 60)
    
    sim = MLMSimulation({
        'line_thresholds': {2: 0.30, 3: 0.20, 4: 0.10, 5: 0.05}
    })
    
    # Create user with known leg distribution
    user = User(user_id=1, level=1, sponsor_id=None)
    
    # Test Case 1: Should qualify for 2 lines
    # Total: 100, Legs: [40, 25, 20, 10, 5]
    user.leg_vps = [40, 25, 20, 10, 5]
    user.total_vp = 100
    sim.users = {1: user}
    sim.determine_line_qualification()
    
    print("Test Case 1: Legs [40, 25, 20, 10, 5], Total 100")
    print(f"  Line 1: 40/100 = 40% (always qualifies)")
    print(f"  Line 2: 25/100 = 25% < 30%, combine: (25+20)/100 = 45% >= 30% ✓")
    print(f"  Qualified lines: {user.qualified_lines} (expected: 2)")
    assert user.qualified_lines == 2, "Should qualify for 2 lines"
    
    # Test Case 2: Should qualify for 4 lines
    # Total: 100, Legs: [35, 30, 20, 10, 5]
    user.leg_vps = [35, 30, 20, 10, 5]
    user.total_vp = 100
    sim.determine_line_qualification()
    
    print("\nTest Case 2: Legs [35, 30, 20, 10, 5], Total 100")
    print(f"  Line 1: 35/100 = 35% ✓")
    print(f"  Line 2: 30/100 = 30% >= 30% ✓")
    print(f"  Line 3: 20/100 = 20% >= 20% ✓")
    print(f"  Line 4: 10/100 = 10% >= 10% ✓")
    print(f"  Line 5: 5/100 = 5% >= 5% ✓")
    print(f"  Qualified lines: {user.qualified_lines} (expected: 5)")
    assert user.qualified_lines == 5, "Should qualify for 5 lines"
    
    print("✓ Line Qualification PASSED\n")


def test_powerup_bonus():
    """Test PowerUp bonus differential calculation"""
    print("=" * 60)
    print("TEST 4: PowerUp Bonus Calculation")
    print("=" * 60)
    
    config = {
        'powerup_matrix': {
            'N4': {1: 0.06, 2: 0.11, 3: 0.13, 4: 0.15},
            'N5': {1: 0.07, 2: 0.13, 3: 0.15, 4: 0.17, 5: 0.19},
            'N7': {1: 0.09, 2: 0.15, 3: 0.19, 4: 0.21, 5: 0.23}
        }
    }
    
    sim = MLMSimulation(config)
    
    # Setup chain: D(10%) -> C(15%) -> B(19%) -> A(21%) -> Purchaser($100)
    user_a = User(user_id=1, level=1, sponsor_id=None)
    user_a.rank = 'N7'
    user_a.qualified_lines = 5
    user_a.powerup_percentage = 0.21
    
    user_b = User(user_id=2, level=2, sponsor_id=1)
    user_b.rank = 'N5'
    user_b.qualified_lines = 5
    user_b.powerup_percentage = 0.19
    
    user_c = User(user_id=3, level=3, sponsor_id=2)
    user_c.rank = 'N5'
    user_c.qualified_lines = 3
    user_c.powerup_percentage = 0.15
    
    user_d = User(user_id=4, level=4, sponsor_id=3)
    user_d.rank = 'N4'
    user_d.qualified_lines = 2
    user_d.powerup_percentage = 0.10
    
    purchaser = User(user_id=5, level=5, sponsor_id=4, purchase_amount=100)
    
    sim.users = {1: user_a, 2: user_b, 3: user_c, 4: user_d, 5: purchaser}
    
    # Calculate bonus
    upline_chain = [4, 3, 2, 1]  # D, C, B, A
    sim._calculate_matching_for_purchase_detailed(100, upline_chain)
    
    print("Chain: A(21%) -> B(19%) -> C(15%) -> D(10%) -> Purchaser($100)")
    print(f"D earnings: ${user_d.total_powerup_earned:.2f} (expected: $10.00)")
    print(f"C earnings: ${user_c.total_powerup_earned:.2f} (expected: $5.00)")
    print(f"B earnings: ${user_b.total_powerup_earned:.2f} (expected: $4.00)")
    print(f"A earnings: ${user_a.total_powerup_earned:.2f} (expected: $2.00)")
    print(f"Total paid: ${user_a.total_powerup_earned + user_b.total_powerup_earned + user_c.total_powerup_earned + user_d.total_powerup_earned:.2f} (expected: $21.00)")
    
    # Allow small floating point tolerance
    tolerance = 0.01
    assert abs(user_d.total_powerup_earned - 10.0) < tolerance
    assert abs(user_c.total_powerup_earned - 5.0) < tolerance
    assert abs(user_b.total_powerup_earned - 4.0) < tolerance
    assert abs(user_a.total_powerup_earned - 2.0) < tolerance
    
    print("✓ PowerUp Bonus PASSED\n")


def test_matching_bonus():
    """Test Matching bonus with cascading"""
    print("=" * 60)
    print("TEST 5: Matching Bonus Calculation")
    print("=" * 60)
    
    config = {
        'powerup_matrix': {
            'N5': {1: 0.07, 2: 0.13, 3: 0.15, 4: 0.17, 5: 0.19},
            'N6': {1: 0.08, 2: 0.14, 3: 0.17, 4: 0.19, 5: 0.21},
            'N7': {1: 0.09, 2: 0.15, 3: 0.19, 4: 0.21, 5: 0.23}
        },
        'matching_percentages': {
            'N5': 0.15,
            'N6': 0.20,
            'N7': 0.25
        }
    }
    
    sim = MLMSimulation(config)
    
    # Chain: A(19%, 15% match) -> B(19%, 20% match) -> C(21%, 15% match) -> Purchaser($100)
    user_a = User(user_id=1, level=1, sponsor_id=None)
    user_a.rank = 'N5'
    user_a.qualified_lines = 5
    user_a.powerup_percentage = 0.19
    user_a.matching_percentage = 0.15
    
    user_b = User(user_id=2, level=2, sponsor_id=1)
    user_b.rank = 'N6'
    user_b.qualified_lines = 5
    user_b.powerup_percentage = 0.19
    user_b.matching_percentage = 0.20
    
    user_c = User(user_id=3, level=3, sponsor_id=2)
    user_c.rank = 'N7'
    user_c.qualified_lines = 5
    user_c.powerup_percentage = 0.21
    user_c.matching_percentage = 0.15
    
    purchaser = User(user_id=4, level=4, sponsor_id=3, purchase_amount=100)
    
    sim.users = {1: user_a, 2: user_b, 3: user_c, 4: purchaser}
    
    # Calculate bonuses
    upline_chain = [3, 2, 1]
    sim._calculate_matching_for_purchase_detailed(100, upline_chain)
    
    print("Chain: A(19%, 15% match) -> B(19%, 20% match) -> C(21%, 15% match) -> Purchase($100)")
    print(f"\nPowerUp:")
    print(f"  C: ${user_c.total_powerup_earned:.2f} (expected: $21.00)")
    print(f"  B: ${user_b.total_powerup_earned:.2f} (expected: $0.00 - lower %)")
    print(f"  A: ${user_a.total_powerup_earned:.2f} (expected: $0.00 - equal %)")
    
    print(f"\nMatching:")
    print(f"  B matches C: ${user_b.total_matching_earned:.2f} (expected: $4.20 = 20% of $21)")
    print(f"  A matches B: ${user_a.total_matching_earned:.2f} (expected: $0.63 = 15% of $4.20)")
    
    tolerance = 0.01
    assert abs(user_c.total_powerup_earned - 21.0) < tolerance
    assert abs(user_b.total_matching_earned - 4.20) < tolerance
    assert abs(user_a.total_matching_earned - 0.63) < tolerance
    
    print("✓ Matching Bonus PASSED\n")


def run_all_tests():
    """Run complete test suite"""
    print("\n" + "=" * 60)
    print("MLM SIMULATION - VALIDATION TEST SUITE")
    print("=" * 60 + "\n")
    
    try:
        test_vp_calculation()
        test_leg_vp_calculation()
        test_line_qualification()
        test_powerup_bonus()
        test_matching_bonus()
        
        print("=" * 60)
        print("ALL TESTS PASSED ✓")
        print("Simulation logic is mathematically accurate")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()
