import random
import math

# Engagement rates for different troop types
ENGAGEMENT_RATES = {
    'Infantry': 3,
    'Lancer': 1,
    'Marksman': 1
}

class Skill:
    def __init__(self, name, effect_type, value, chance, target=None, duration=1, once_per_battle=False, kills=0, max_uses=float('inf'), phase='any'):
        self.name = name
        self.effect_type = effect_type  # e.g., 'damage_increase', 'stun', etc.
        self.value = value
        self.chance = chance  # Probability to trigger (as a decimal)
        self.target = target
        self.duration = duration  # Duration of the effect in turns
        self.activation_count = 0
        self.once_per_battle = once_per_battle
        self.kills = kills
        self.max_uses = max_uses  # Maximum times the skill can be activated per battle
        self.phase = phase  # Battle phase: 'start', 'middle', 'end', or 'any'

    def try_activate(self):
        if self.once_per_battle and self.activation_count > 0:
            return False
        if self.activation_count >= self.max_uses:
            return False
        activated = random.random() <= min(self.chance, 1.0)
        if activated:
            self.activation_count += 1
        return activated

class TroopType:
    def __init__(self, name, base_attack, base_defense, base_lethality, base_health, count, bonuses, static_skills, rng_skills, position, initiative=1):
        self.name = name
        self.base_attack = base_attack
        self.base_defense = base_defense
        self.base_lethality = base_lethality
        self.base_health = base_health
        self.count = count
        self.initial_count = count
        self.bonuses = bonuses.copy()  # Dict with keys: attack, defense, lethality, health (percentages)
        self.static_skills = static_skills  # List of always-active Skill objects
        self.rng_skills = rng_skills  # List of RNG Skill
        self.position = position  # 'Front', 'Middle', 'Back'
        self.initiative = initiative
        self.effective_stats = self.calculate_effective_stats()
        self.total_health = self.effective_stats['health'] * self.count
        self.alive = True
        self.kills = 0
        # Status effects
        self.status_effects = {}
        # Injury tracking
        self.lightly_injured = 0
        self.severely_injured = 0

    def calculate_effective_stats(self):
        effective_attack = self.base_attack * (1 + self.bonuses.get('attack', 0) / 100)
        effective_defense = self.base_defense * (1 + self.bonuses.get('defense', 0) / 100)
        effective_lethality = self.base_lethality * (1 + self.bonuses.get('lethality', 0) / 100)
        effective_health = self.base_health * (1 + self.bonuses.get('health', 0) / 100)
        return {
            'attack': effective_attack,
            'defense': effective_defense,
            'lethality': effective_lethality,
            'health': effective_health
        }

class Army:
    def __init__(self, name, troops, hero_skills):
        self.name = name
        self.troops = troops
        self.hero_skills = hero_skills
        self.skill_activation_log = {}
        self.status_effects = {}  # For army-wide status effects
        self.update_total_health()
        self.apply_once_skills()

    def update_total_health(self):
        self.total_health = sum([troop.total_health for troop in self.troops.values() if troop.alive])

    def is_defeated(self):
        return all(not troop.alive for troop in self.troops.values())

    def get_frontline(self):
        for position in ['Front', 'Middle', 'Back']:
            frontline_troops = [troop for troop in self.troops.values() if troop.position == position and troop.alive]
            if frontline_troops:
                return frontline_troops
        return []

    def apply_once_skills(self):
        for skill in self.hero_skills:
            if skill.once_per_battle:
                # Apply the skill effects globally to all troops
                self.skill_activation_log[skill.name] = 1
                for troop in self.troops.values():
                    if skill.effect_type == 'damage_increase':
                        troop.bonuses['attack'] = troop.bonuses.get('attack', 0) + skill.value
                    elif skill.effect_type == 'defense_increase':
                        troop.bonuses['defense'] = troop.bonuses.get('defense', 0) + skill.value
                    elif skill.effect_type == 'health_increase':
                        troop.bonuses['health'] = troop.bonuses.get('health', 0) + skill.value
                    # Recalculate effective stats
                    troop.effective_stats = troop.calculate_effective_stats()

def calculate_damage(attacker, defender, damage_modifiers, attacker_army, defender_army):
    attack = attacker.effective_stats['attack']
    lethality = attacker.effective_stats['lethality']
    defense = defender.effective_stats['defense']

    # Apply damage decrease from defender's status effects
    if 'damage_decrease' in defender.status_effects:
        defense *= (1 + defender.status_effects['damage_decrease']['value'] / 100)

    # Apply army-wide damage decrease (e.g., from 'Iron Strength')
    if 'damage_decrease' in defender_army.status_effects:
        defense *= (1 + defender_army.status_effects['damage_decrease']['value'] / 100)

    # Compute base damage per troop
    base_damage = attack * (1 + lethality / 100)

    # Apply damage modifiers
    total_damage_modifiers = sum(damage_modifiers) / 100
    base_damage *= (1 + total_damage_modifiers)

    # Apply defense
    defense_factor = defense + 1
    damage_per_troop = base_damage / defense_factor

    # Apply random variance
    damage_variance = random.uniform(0.9, 1.1)
    damage_per_troop *= damage_variance

    # Apply engagement rate
    engagement_rate = ENGAGEMENT_RATES.get(attacker.name, 0.5)
    number_of_attackers = max(1, int(attacker.count * engagement_rate))

    # Total damage is per-troop damage times number of engaged troops
    total_damage = damage_per_troop * number_of_attackers

    return total_damage, number_of_attackers

def apply_damage(defender, damage, attacker=None, skill=None, number_of_attackers=1):
    # Distribute damage across defender's troops
    troops_lost = min(defender.count, damage / defender.effective_stats['health'])
    defender.count -= troops_lost
    defender.total_health -= damage

    # Determine injury types based on game mechanics
    if troops_lost > 0:
        lightly_injured_ratio = 0.65  # Adjusted based on game data
        severely_injured_ratio = 0.35
        lightly_injured = troops_lost * lightly_injured_ratio
        severely_injured = troops_lost * severely_injured_ratio
        defender.lightly_injured += lightly_injured
        defender.severely_injured += severely_injured

    if defender.count <= 0:
        defender.alive = False

    # Track kills
    if attacker:
        attacker.kills += troops_lost
        if skill:
            skill.kills += troops_lost

def apply_status_effects(troop, battle_log):
    to_remove = []
    for effect_name, effect in troop.status_effects.items():
        if effect_name == 'burn':
            # Burn damage is already calculated and stored when applied
            total_burn_damage = effect['damage']
            apply_damage(troop, total_burn_damage)
            battle_log.append(f"{troop.name} takes {total_burn_damage:.2f} burn damage from burn effect.")

        effect['remaining_turns'] -= 1
        if effect['remaining_turns'] <= 0:
            to_remove.append(effect_name)
    for effect_name in to_remove:
        del troop.status_effects[effect_name]
    if troop.count <= 0:
        troop.alive = False

def apply_army_status_effects(army, battle_log):
    to_remove = []
    for effect_name, effect in army.status_effects.items():
        effect['remaining_turns'] -= 1
        if effect['remaining_turns'] <= 0:
            to_remove.append(effect_name)
    for effect_name in to_remove:
        del army.status_effects[effect_name]

def simulate_battle(army_a, army_b, max_turns=100):
    turn = 0
    battle_log = []
    while turn < max_turns and not army_a.is_defeated() and not army_b.is_defeated():
        turn += 1
        turn_log = f"\n--- Turn {turn} ---"
        battle_log.append(turn_log)

        # Apply status effects at the start of the turn
        for army in [army_a, army_b]:
            for troop in army.troops.values():
                if troop.alive:
                    apply_status_effects(troop, battle_log)
            apply_army_status_effects(army, battle_log)

        # Determine attack order based on initiative
        all_troops = [(army_a, troop) for troop in army_a.troops.values() if troop.alive] + \
                     [(army_b, troop) for troop in army_b.troops.values() if troop.alive]
        all_troops.sort(key=lambda x: x[1].initiative, reverse=True)

        for army, attacker in all_troops:
            defender_army = army_b if army == army_a else army_a
            frontline_targets = defender_army.get_frontline()
            if not frontline_targets:
                continue  # No targets left

            if 'stun' in attacker.status_effects:
                attacker.status_effects['stun']['remaining_turns'] -= 1
                if attacker.status_effects['stun']['remaining_turns'] <= 0:
                    del attacker.status_effects['stun']
                battle_log.append(f"{army.name}'s {attacker.name} is stunned and cannot act this turn.")
                continue

            # Default target is the frontline troop
            target = frontline_targets[0]

            # Adjust target for skills or troop types
            special_target = False

            # Static troop-specific skills
            damage_modifiers = []
            for skill in attacker.static_skills:
                if skill.effect_type == 'damage_increase' and (skill.target == target.name or skill.target == 'All'):
                    damage_modifiers.append(skill.value)

            # RNG skills
            apply_burn = False  # Initialize apply_burn flag
            multi_attack = False  # Initialize multi_attack flag
            for skill in attacker.rng_skills + [s for s in army.hero_skills if not s.once_per_battle]:
                if skill.try_activate():
                    army.skill_activation_log[skill.name] = army.skill_activation_log.get(skill.name, 0) + 1
                    if skill.effect_type == 'damage_increase' and (skill.target == target.name or skill.target == 'All'):
                        damage_modifiers.append(skill.value)
                        battle_log.append(f"{attacker.name}'s skill '{skill.name}' activated!")
                    elif skill.effect_type == 'burn':
                        # Burn damage is 40% of initial damage dealt, per turn, for 3 turns
                        # We will calculate burn damage after the attack
                        apply_burn = True
                        burn_skill = skill
                    elif skill.effect_type == 'stun':
                        if 'stun' not in target.status_effects:
                            target.status_effects['stun'] = {'remaining_turns': skill.duration}
                            battle_log.append(f"{attacker.name}'s skill '{skill.name}' activated! {target.name} is stunned.")
                    elif skill.effect_type == 'damage_taken_increase':
                        if 'damage_taken_increase' not in target.status_effects:
                            target.status_effects['damage_taken_increase'] = {'value': skill.value, 'remaining_turns': skill.duration}
                            battle_log.append(f"{attacker.name}'s skill '{skill.name}' activated! {target.name} takes increased damage.")
                    elif skill.effect_type == 'damage_decrease':
                        if 'damage_decrease' not in defender_army.status_effects:
                            defender_army.status_effects['damage_decrease'] = {'value': skill.value, 'remaining_turns': skill.duration}
                            battle_log.append(f"{attacker.name}'s skill '{skill.name}' activated! {defender_army.name}'s troops deal less damage.")
                    elif skill.effect_type == 'direct_attack':
                        # Target the specific troop type regardless of frontline
                        target_troop = defender_army.troops.get(skill.target)
                        if target_troop and target_troop.alive:
                            target = target_troop
                            special_target = True
                            battle_log.append(f"{attacker.name}'s skill '{skill.name}' activated! Attacking {target.name} directly.")
                    elif skill.effect_type == 'multi_attack':
                        # Handle multi-attack logic
                        multi_attack = True
                        battle_log.append(f"{attacker.name}'s skill '{skill.name}' activated! Attacking multiple times.")

            # Apply damage taken increase debuff
            if 'damage_taken_increase' in target.status_effects:
                damage_modifiers.append(target.status_effects['damage_taken_increase']['value'])

            # Calculate damage
            damage, number_of_attackers = calculate_damage(attacker, target, damage_modifiers, army, defender_army)
            apply_damage(target, damage, attacker, skill, number_of_attackers)
            battle_log.append(f"{army.name}'s {attacker.name} attacks {defender_army.name}'s {target.name} with {number_of_attackers} troops, dealing {damage:.2f} damage.")

            # Apply burn effect after damage calculation
            if apply_burn:
                burn_damage = damage * (burn_skill.value / 100)
                if 'burn' not in target.status_effects:
                    target.status_effects['burn'] = {'damage': burn_damage, 'remaining_turns': burn_skill.duration}
                    battle_log.append(f"{attacker.name}'s skill '{burn_skill.name}' activated! {target.name} is burning.")
                else:
                    # If burn is already active, sum the burn damage
                    target.status_effects['burn']['damage'] += burn_damage
                    target.status_effects['burn']['remaining_turns'] = burn_skill.duration
                apply_burn = False  # Reset flag

            # Check if target is defeated
            if not target.alive:
                battle_log.append(f"{defender_army.name}'s {target.name} has been defeated!")
                defender_army.update_total_health()

            # Handle multi-attack if applicable
            if multi_attack and target.alive:
                # Perform a second attack
                damage, number_of_attackers = calculate_damage(attacker, target, damage_modifiers, army, defender_army)
                apply_damage(target, damage, attacker, skill, number_of_attackers)
                battle_log.append(f"{army.name}'s {attacker.name} attacks again, dealing {damage:.2f} damage.")
                multi_attack = False  # Reset flag

            # Apply status effects to the army if any
            # (Already handled in the skill activation loop)

        # Check for victory
        if army_a.is_defeated() or army_b.is_defeated():
            break

    # Determine winner
    if army_a.is_defeated() and army_b.is_defeated():
        winner = "Draw"
    elif army_b.is_defeated():
        winner = army_a.name
    else:
        winner = army_b.name

    # Generate battle report
    battle_report = generate_battle_report(army_a, army_b, winner, turn)
    battle_log.append(battle_report)

    # Print battle log
    for entry in battle_log:
        print(entry)

def generate_battle_report(army_a, army_b, winner, total_turns):
    report = f"\n--- Battle Report ---\n"
    report += f"Total Turns: {total_turns}\n"
    report += f"Winner: {winner}\n\n"
    for army in [army_a, army_b]:
        report += f"Army: {army.name}\n"
        total_kills = sum([troop.kills for troop in army.troops.values()])
        total_injured = sum([troop.lightly_injured + troop.severely_injured for troop in army.troops.values()])
        survivors = sum([troop.count for troop in army.troops.values()])
        report += f"  Total Kills: {int(total_kills)}\n"
        report += f"  Total Injured: {int(total_injured)}\n"
        report += f"  Survivors: {int(survivors)}\n"
        for troop in army.troops.values():
            casualties = int(troop.initial_count - troop.count) if troop.count >= 0 else troop.initial_count
            remaining = int(troop.count) if troop.count >= 0 else 0
            report += f"  {troop.name}:\n"
            report += f"    Kills: {int(troop.kills)}\n"
            report += f"    Starting Count: {troop.initial_count}\n"
            report += f"    Remaining: {remaining}\n"
            report += f"    Lightly Injured: {int(troop.lightly_injured)}\n"
            report += f"    Severely Injured: {int(troop.severely_injured)}\n"
        report += f"  Skills Activated:\n"
        for skill_name, count in army.skill_activation_log.items():
            report += f"    {skill_name}: {count} times\n"
        report += "\n"
    return report

# Create troops for Dave
dave_infantry = TroopType(
    name='Infantry',
    base_attack=10,
    base_defense=13,
    base_lethality=10,
    base_health=15,
    count=331624,
    bonuses={'attack': 904.6, 'defense': 690.5, 'lethality': 1065.1, 'health': 1181.8},
    static_skills=[Skill("Master Brawler", "damage_increase", 10, 1.0, target="Lancer")],
    rng_skills=[],
    position='Front'
)

dave_lancer = TroopType(
    name='Lancer',
    base_attack=13,
    base_defense=11,
    base_lethality=14,
    base_health=11,
    count=317817,
    bonuses={'attack': 830.8, 'defense': 643.9, 'lethality': 849.6, 'health': 943.1},
    static_skills=[Skill("Charge", "damage_increase", 10, 1.0, target="Marksman")],
    rng_skills=[Skill("Ambusher", "direct_attack", 0, 0.2, target="Marksman")],
    position='Middle'
)

dave_marksman = TroopType(
    name='Marksman',
    base_attack=14,
    base_defense=10,
    base_lethality=15,
    base_health=10,
    count=50366,
    bonuses={'attack': 826.5, 'defense': 638.5, 'lethality': 847.8, 'health': 956.6},
    static_skills=[Skill("Ranged Strike", "damage_increase", 10, 1.0, target="Infantry")],
    rng_skills=[Skill("Volley", "multi_attack", 0, 0.1)],
    position='Back'
)

# Create troops for Brabo
brabo_infantry = TroopType(
    name='Infantry',
    base_attack=10,
    base_defense=13,
    base_lethality=10,
    base_health=15,
    count=474098,
    bonuses={'attack': 779.5, 'defense': 690.5, 'lethality': 989.2, 'health': 824.7},
    static_skills=[Skill("Master Brawler", "damage_increase", 10, 1.0, target="Lancer")],
    rng_skills=[],
    position='Front'
)

brabo_lancer = TroopType(
    name='Lancer',
    base_attack=13,
    base_defense=11,
    base_lethality=14,
    base_health=11,
    count=232514,
    bonuses={'attack': 699.1, 'defense': 615.0, 'lethality': 852.3, 'health': 712.8},
    static_skills=[Skill("Charge", "damage_increase", 10, 1.0, target="Marksman")],
    rng_skills=[Skill("Ambusher", "direct_attack", 0, 0.2, target="Marksman")],
    position='Middle'
)

brabo_marksman = TroopType(
    name='Marksman',
    base_attack=14,
    base_defense=10,
    base_lethality=15,
    base_health=10,
    count=309520,
    bonuses={'attack': 749.7, 'defense': 661.5, 'lethality': 907.6, 'health': 752.1},
    static_skills=[Skill("Ranged Strike", "damage_increase", 10, 1.0, target="Infantry")],
    rng_skills=[Skill("Volley", "multi_attack", 0, 0.1)],
    position='Back'
)

# Assemble armies
dave_troops = {
    'Infantry': dave_infantry,
    'Lancer': dave_lancer,
    'Marksman': dave_marksman
}

brabo_troops = {
    'Infantry': brabo_infantry,
    'Lancer': brabo_lancer,
    'Marksman': brabo_marksman
}

# Add hero skills to the armies
dave_army = Army(name='Dave', troops=dave_troops, hero_skills=[
    Skill("Burning Resolve", "damage_increase", 25, 1.0, target="All", once_per_battle=True),
    Skill("Vigor Tactics", "damage_increase", 15, 1.0, target="All", once_per_battle=True),
    Skill("Implacable", "health_increase", 10, 1.0, target="All", once_per_battle=True),
    Skill("Positional Battler", "damage_increase", 25, 1.0, target="All", once_per_battle=True),
    Skill("Dosage Boost", "damage_increase", 200, 0.24, target="All", duration=1),
    Skill("Numbing Spores", "stun", 0, 0.2, target="All", duration=1),
    Skill("Pyromaniac", "burn", 40, 0.2, target="All", duration=3),
    Skill("Immolation", "damage_taken_increase", 50, 0.5, target="All", duration=1)
])

brabo_army = Army(name='Brabo', troops=brabo_troops, hero_skills=[
    Skill("Battle Manifesto", "damage_increase", 25, 1.0, target="All", once_per_battle=True),
    Skill("Sword Mentor", "damage_increase", 25, 1.0, target="All", once_per_battle=True),
    Skill("Vigor Tactics", "damage_increase", 15, 1.0, target="All", once_per_battle=True),
    Skill("Dosage Boost", "damage_increase", 200, 0.37, target="All", duration=1),
    Skill("Numbing Spores", "stun", 0, 0.2, target="All", duration=1),
    Skill("Onslaught", "stun", 0, 0.2, target="All", duration=1),
    Skill("Iron Strength", "damage_decrease", 50, 0.25, target="All", duration=2),
    Skill("Poison Harpoon", "damage_increase", 50, 0.63, target="All", duration=1),
    Skill("Expert Swordsmanship", "stun", 0, 0.2, target="All", duration=1)
])

# Simulate the battle
simulate_battle(dave_army, brabo_army)
