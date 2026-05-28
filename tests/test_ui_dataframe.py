import unittest

import pandas as pd

from ui.dataframe import build_display_dataframe


class DataframeDisplayTests(unittest.TestCase):
    def test_ratio_columns_render_without_name_error(self) -> None:
        df = pd.DataFrame(
            [
                {"gender": "女", "female_percent": 47.49},
                {"gender": "男", "female_percent": 52.51},
            ]
        )

        display_df = build_display_dataframe(df)

        self.assertEqual(list(display_df.columns), ["\u6027\u522b", "\u5973\u6027\u5360\u6bd4"])

    def test_unknown_ratio_column_uses_ratio_label(self) -> None:
        df = pd.DataFrame([{"gender": "女", "gender_ratio": 47.49}])

        display_df = build_display_dataframe(df)

        self.assertEqual(list(display_df.columns), ["\u6027\u522b", "\u5360\u6bd4"])


if __name__ == "__main__":
    unittest.main()
