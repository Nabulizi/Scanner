import unittest

from config import DEFAULT_RULES, RISK_GATES
from models import ScoreResult, SignalResult
from scoring import score_signals


def clean_long_signals():
    return {
        'direction': 'long',
        'fvg': {'bullish': {'price_inside': True}, 'bearish': None},
        'near_lower_bb': True,
        'near_upper_bb': False,
        'bb_expanding': False,
        'stoch_oversold_cross': True,
        'stoch_overbought_cross': False,
        'stoch_mid_range': False,
        'earnings_soon': False,
    }


def clean_portfolio():
    return {
        'daily_chart_checked': True,
        'no_strong_downtrend': True,
        'no_strong_uptrend': True,
        'fed_day': False,
        'tesla_catalyst': False,
        'initial_size_confirmed': True,
        'open_positions': 0,
        'total_deployed': 0,
        'max_avgdown_defined': True,
        'profit_target_confirmed': True,
        'hard_stop_confirmed': True,
        'position_size': 3_000,
        'max_total_deployed': 60_000,
        'max_open_positions': 2,
        'max_stock_position': 10_000,
        'max_tsll_tslz_position': 6_000,
    }


class ScoreSignalsTest(unittest.TestCase):
    def test_config_exposes_named_risk_gates(self):
        self.assertEqual(DEFAULT_RULES['max_total_deployed'], 60_000)
        self.assertIn('total_under_deployed_limit', RISK_GATES)
        self.assertNotIn('total_under_60k', RISK_GATES)

    def test_models_are_importable_contracts(self):
        self.assertIsNotNone(SignalResult)
        self.assertIsNotNone(ScoreResult)

    def test_total_deployed_limit_is_a_hard_blocker(self):
        portfolio = clean_portfolio()
        portfolio['total_deployed'] = 60_000

        result = score_signals('TEST', clean_long_signals(), portfolio)

        self.assertEqual(result['verdict'], 'SKIP')
        self.assertFalse(result['checks']['total_under_deployed_limit'])
        self.assertIn('Total deployed at or above $60,000', result['hard_blockers'])

    def test_total_deployed_limit_comes_from_portfolio_state(self):
        portfolio = clean_portfolio()
        portfolio['max_total_deployed'] = 12_000
        portfolio['total_deployed'] = 12_000

        result = score_signals('TEST', clean_long_signals(), portfolio)

        self.assertEqual(result['verdict'], 'SKIP')
        self.assertIn('Total deployed at or above $12,000', result['hard_blockers'])

    def test_position_cap_comes_from_portfolio_state(self):
        portfolio = clean_portfolio()
        portfolio['max_stock_position'] = 4_000
        portfolio['position_size'] = 5_000

        result = score_signals('TEST', clean_long_signals(), portfolio, 'stock')

        self.assertEqual(result['verdict'], 'SKIP')
        self.assertIn('Position size exceeds $4,000 stock cap', result['hard_blockers'])

    def test_result_splits_core_risk_and_checklist_scores(self):
        result = score_signals('TEST', clean_long_signals(), clean_portfolio())

        self.assertEqual(result['score_sections']['core_setup'], '3/3')
        self.assertEqual(result['score_sections']['risk_gates'], '6/6')
        self.assertEqual(result['score_sections']['checklist'], '25/25')

    def test_clean_trade_has_no_blockers_and_has_reason_for_each_check(self):
        result = score_signals('TEST', clean_long_signals(), clean_portfolio())

        self.assertEqual(result['verdict'], 'TAKE')
        self.assertEqual(result['hard_blockers'], [])
        self.assertEqual(result['blocker_reasons'], [])
        self.assertEqual(len(result['check_reasons']), result['total'])
        self.assertIn(
            {'key': 'bb_signal', 'passed': True, 'label': 'Bollinger Band confirmation'},
            result['check_reasons'],
        )

    def test_invalid_price_data_is_a_hard_blocker(self):
        signals = clean_long_signals()
        signals['data_quality'] = {
            'valid': False,
            'warnings': ['Not enough 1H candles'],
        }

        result = score_signals('TEST', signals, clean_portfolio())

        self.assertEqual(result['verdict'], 'SKIP')
        self.assertIn(
            'Price data unavailable or incomplete: Not enough 1H candles',
            result['hard_blockers'],
        )


if __name__ == '__main__':
    unittest.main()
