import unittest

import pandas as pd

from indicators import detect_fvg, infer_direction


def frame(rows):
    return pd.DataFrame(rows)


class IndicatorsTest(unittest.TestCase):
    def test_unfilled_bullish_fvg_is_detected(self):
        df = frame([
            {'High': 10.0, 'Low': 8.0, 'Close': 9.5},
            {'High': 10.5, 'Low': 9.0, 'Close': 10.0},
            {'High': 12.0, 'Low': 11.0, 'Close': 11.5},
            {'High': 11.2, 'Low': 10.4, 'Close': 10.8},
            {'High': 10.9, 'Low': 10.3, 'Close': 10.5},
        ])

        result = detect_fvg(df, lookback=5)

        self.assertIsNotNone(result['bullish'])
        self.assertEqual(result['bullish']['gap_bottom'], 10.0)
        self.assertEqual(result['bullish']['gap_top'], 11.0)

    def test_filled_bullish_fvg_is_ignored(self):
        df = frame([
            {'High': 10.0, 'Low': 8.0, 'Close': 9.5},
            {'High': 10.5, 'Low': 9.0, 'Close': 10.0},
            {'High': 12.0, 'Low': 11.0, 'Close': 11.5},
            {'High': 11.2, 'Low': 9.9, 'Close': 10.8},
            {'High': 10.9, 'Low': 10.3, 'Close': 10.5},
        ])

        result = detect_fvg(df, lookback=5)

        self.assertIsNone(result['bullish'])

    def test_filled_bearish_fvg_is_ignored(self):
        df = frame([
            {'High': 12.0, 'Low': 10.0, 'Close': 11.0},
            {'High': 11.0, 'Low': 9.5, 'Close': 10.0},
            {'High': 9.0, 'Low': 8.0, 'Close': 8.5},
            {'High': 10.1, 'Low': 9.0, 'Close': 9.4},
            {'High': 9.7, 'Low': 9.0, 'Close': 9.5},
        ])

        result = detect_fvg(df, lookback=5)

        self.assertIsNone(result['bearish'])

    def test_direction_uses_stronger_confluence(self):
        last = pd.Series({
            'near_lower_bb': True,
            'near_upper_bb': False,
            'stoch_oversold_cross': True,
            'stoch_overbought_cross': False,
        })

        direction = infer_direction(last, {'bullish': {'price_inside': True}, 'bearish': None})

        self.assertEqual(direction, 'long')


if __name__ == '__main__':
    unittest.main()
