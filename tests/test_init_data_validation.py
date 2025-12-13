import unittest

from astro_api.telegram_webapp_auth import (
    compute_hash,
    build_data_check_string,
    parse_init_data,
)


class InitDataValidationTest(unittest.TestCase):
    def test_known_example(self):
        bot_token = "5768337691:AAH5YkoiEuPk8-FZa32hStHTqXiLPtAEhx8"
        init_data = (
            "query_id=AAHdF6IQAAAAAN0XohDhrOrc&user=%7B%22id%22%3A279058397%2C%22first_name%22%3A%22Vladislav%22%2C%22last_name%22%3A%22Kibenko%22%2C%22username%22%3A%22vdkfrost%22%2C%22language_code%22%3A%22ru%22%2C%22is_premium%22%3Atrue%7D"
            "&auth_date=1662771648&hash=c501b71e775f74ce10e377dea85a7ea24ecd640b223ea86dfe453e0eaed2e2b2"
        )
        pairs = parse_init_data(init_data)
        data_check_string, received_hash = build_data_check_string(pairs)
        self.assertEqual(received_hash, "c501b71e775f74ce10e377dea85a7ea24ecd640b223ea86dfe453e0eaed2e2b2")
        computed = compute_hash(bot_token, data_check_string)
        self.assertEqual(computed, received_hash)

    def test_hash_mismatch(self):
        bot_token = "5768337691:AAH5YkoiEuPk8-FZa32hStHTqXiLPtAEhx8"
        init_data = (
            "query_id=AAHdF6IQAAAAAN0XohDhrOrc&user=%7B%22id%22%3A279058397%7D"
            "&auth_date=1662771649&hash=c501b71e775f74ce10e377dea85a7ea24ecd640b223ea86dfe453e0eaed2e2b2"
        )
        pairs = parse_init_data(init_data)
        data_check_string, received_hash = build_data_check_string(pairs)
        computed = compute_hash(bot_token, data_check_string)
        self.assertNotEqual(computed, received_hash)


if __name__ == "__main__":
    unittest.main()
