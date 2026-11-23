"""
world/weather.py — Markov Chain Micro-Climate Simulator
=======================================================

Simulates stochastic RSU micro-climate state transitions (Sunny, Cloudy, Rainy)
and thermal inertia for highway road segments.
"""

import copy
import random
from typing import Any, Dict, List


class Weather:
    """Markov-chain micro-climate weather and thermal inertia simulator for a single RSU zone."""

    def __init__(self, params: Dict[str, Any]) -> None:
        self.params: Dict[str, Any] = params
        self.transition_probabilities: Dict[str, Any] = copy.deepcopy(self.params['TransitionProbabilities'])
        for transition_from in self.transition_probabilities.values():
            for state, value in transition_from['TransitionTo'].items():
                transition_from['TransitionTo'][state] = value * self.params['UpdatePeriod'] / 20
        self.previous_state: str = 'Sunny'
        self.current_state: str = 'Sunny'
        self.last_transition: List[str] = []

        self.air_temp: float = float(self.params['StandardTemp']['Air'][self.current_state])
        self.sunny_weather_effect: float = 0.5
        self.road_temp: float = self.air_temp + (self.air_temp * 0.6 * self.sunny_weather_effect)
        self.state: Dict[str, Any] = {}
        self.statistic: List[Dict[str, Any]] = []

    def update_state(self, timestamp: str) -> None:
        """Advances weather regime, air temperature, and road surface temperature for one step."""
        if getattr(self, "manual_override", False):
            self.state.update({
                'Timestamp': timestamp,
                'Weather': self.current_state,
                'AirTemperature': self.air_temp,
                'RoadSurfaceTemperature': self.road_temp
            })
            self.statistic.append(copy.deepcopy(self.state))
            if len(self.statistic) > 100:
                self.statistic = self.statistic[-100:]
            return

        self.previous_state = self.current_state
        transitions = self.transition_probabilities.get(self.current_state, {}).get('TransitionTo', {})
        if transitions:
            other_states = list(transitions.keys())
            other_probs = [float(transitions[s]) for s in other_states]
            sum_other = sum(other_probs)
            p_stay = max(0.0, 1.0 - sum_other)
            candidates = [self.current_state] + other_states
            weights = [p_stay] + other_probs
            chosen_state = random.choices(candidates, weights=weights, k=1)[0]
            if chosen_state != self.current_state:
                self.current_state = chosen_state
                self.last_transition = [self.previous_state, self.current_state]

        swe_sign = 1 if self.current_state == 'Sunny' else -1  # Sunny weather effect
        self.sunny_weather_effect = self.sunny_weather_effect + swe_sign * (self.params['UpdatePeriod'] / 3600)
        if self.sunny_weather_effect > 1:
            self.sunny_weather_effect = 1
        elif self.sunny_weather_effect < 0:
            self.sunny_weather_effect = 0
        self.target_air_temp = self.params['StandardTemp']['Air'][self.current_state]
        if self.last_transition == []:
            self.temp_change = 0
        else:
            self.temp_change = -1 if self.params['StandardTemp']['Air'][self.last_transition[0]] - self.params['StandardTemp']['Air'][self.last_transition[1]] > 0 else 1
        self.new_temp = self.air_temp + self.temp_change * (self.params['UpdatePeriod'] / 600 * self.params['TempDynamicChange'])
        for state in ['Sunny', 'Cloudy']:
            if state == self.current_state and self.new_temp - self.params['StandardTemp']['Air'][state] > 0.1 and self.temp_change == 1:
                self.temp_change = -1
                self.new_temp = self.air_temp + self.temp_change * (self.params['UpdatePeriod'] / 600 * self.params['TempDynamicChange'])
        for state in ['Rainy', 'Cloudy']:
            if state == self.current_state and self.new_temp - self.params['StandardTemp']['Air'][state] < - 0.1 and self.temp_change == -1:
                self.temp_change = 1
                self.new_temp = self.air_temp + self.temp_change * (self.params['UpdatePeriod'] / 600 * self.params['TempDynamicChange'])
        self.air_temp = self.new_temp + (0.5 - random.random()) * 0.1
        self.road_temp = self.air_temp + (self.air_temp * 0.6 * self.sunny_weather_effect)
        self.state.update({
            'Timestamp': timestamp,
            'Weather': self.current_state,
            'AirTemperature': self.air_temp,
            'RoadSurfaceTemperature': self.road_temp
        })
        self.statistic.append(copy.deepcopy(self.state))
        if len(self.statistic) > 100:
            self.statistic = self.statistic[-100:]
