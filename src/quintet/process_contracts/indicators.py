"""Technical indicator calculations for contract data.

These methods are copied exactly from data_pipeline to ensure identical results.
The DataFrame must have columns: Settle, High, Low (use normalize_columns first).
"""

import pandas as pd
import numpy as np


class Indicators:
    """Indicator calculations matching data_pipeline exactly."""

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def isclose(series):
        """Check if all floating points in a series are equal to the first value."""
        return np.all(np.isclose(series, series.iloc[0]))

    @staticmethod
    def high_of_day(df):
        """High of day - Settle can be above high."""
        return df[['High', 'Settle']].max(axis=1)

    @staticmethod
    def low_of_day(df):
        """Low of day - Settle can be below low."""
        return df[['Low', 'Settle']].min(axis=1)

    @staticmethod
    def ema(df, window, field='Settle'):
        """Exponential moving average."""
        return df[field].ewm(span=window,
                             min_periods=window,
                             adjust=False).mean()

    @staticmethod
    def sma(df, window, field='Settle'):
        """Simple moving average."""
        return df[field].rolling(window=window,
                                 min_periods=window).mean()

    @staticmethod
    def tr(df):
        """True Range calculation."""
        highs = Indicators.high_of_day(df)
        lows = Indicators.low_of_day(df)
        prev_close = df['Settle'].shift()
        high_minus_low = highs - lows
        high_minus_prevclose = np.abs(highs - prev_close)
        low_minus_prevclose = np.abs(lows - prev_close)
        return pd.concat([high_minus_low, high_minus_prevclose,
                          low_minus_prevclose], axis=1).max(axis=1)

    @staticmethod
    def atr(df, window):
        """Average True Range using EMA smoothing."""
        tr = Indicators.tr(df)
        return tr.ewm(span=window, min_periods=window, adjust=False).mean()

    # =========================================================================
    # Structural Indicators (Support/Resistance)
    # =========================================================================

    @classmethod
    def resistance(cls, df, window):
        """Calculate resistance level.

        At the end of the day look back n days including today.
        Record the highest high (settle can sometimes be above the high).
        If the high has been the same for n days then it is a resistance level.
        """
        _temp_df = pd.DataFrame(
            df[['High', 'Settle']].max(axis=1).rolling(window).max(),
            columns=['Rolling'])
        # If the high has been the same for n days then it is a resistance level
        _temp_df['Jump'] = _temp_df['Rolling'].rolling(
            window).apply(cls.isclose)
        # Get the level and keep it until the next jump
        _temp_df['Level'] = _temp_df['Rolling'][_temp_df['Jump'] == True]
        _temp_df['Level'] = _temp_df['Level'].ffill()
        # The resistance at the end of the day is the max of the rolling level and the high
        _temp_df['Res'] = _temp_df[['Rolling', 'Level']].max(axis=1)
        return _temp_df['Res']

    @classmethod
    def support(cls, df, window):
        """Calculate support level.

        At the end of the day look back n days including today.
        Record the lowest low (settle can sometimes be below the low).
        If the low has been the same for n days then it is a support level.
        """
        _temp_df = pd.DataFrame(
            df[['Low', 'Settle']].min(axis=1).rolling(window).min(),
            columns=['Rolling'])
        # If the low has been the same for n days then it is a support level
        _temp_df['Jump'] = _temp_df['Rolling'].rolling(
            window).apply(cls.isclose)
        # Get the level and keep it until the next jump
        _temp_df['Level'] = _temp_df['Rolling'][_temp_df['Jump'] == True]
        _temp_df['Level'] = _temp_df['Level'].ffill()
        # The support at the end of the day is the min of the rolling level and the low
        _temp_df['Sup'] = _temp_df[['Rolling', 'Level']].min(axis=1)
        return _temp_df['Sup']

    # =========================================================================
    # Technical Indicators
    # =========================================================================

    @staticmethod
    def calculate_sema(df, window):
        """sEMA = (Settle - EMA) / EMA

        Answers where the price is compared to the EMA.
        """
        ema = Indicators.ema(df, window, field='Settle')
        sema = (df['Settle'] - ema) / ema
        return sema

    @staticmethod
    def calculate_natr(df, window):
        """nATR = ATR / Settle

        Normalized ATR as percentage of price.
        """
        atr = Indicators.atr(df, window)
        natr = atr / df['Settle']
        return natr

    @staticmethod
    def calculate_vns(df, window):
        """VNS = (EMA - SMA) / ATR

        Velocity normalized by spread (the correct one).
        """
        fast = Indicators.ema(df, window)
        slow = Indicators.sma(df, window)
        atr = Indicators.atr(df, window)
        vns = (fast - slow) / atr
        return vns

    @staticmethod
    def calculate_mo(df, window):
        """Mo = (EMA - SMA) / SMA

        Momentum (the correct one).
        """
        fast = Indicators.ema(df, window)
        slow = Indicators.sma(df, window)
        mo = (fast - slow) / slow
        return mo
