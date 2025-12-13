"""CLI для быстрой проверки расчёта натальной карты."""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from astro_bot import natal_engine


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug natal chart generation")
    parser.add_argument("--date", required=True, help="Дата рождения ДД.ММ.ГГГГ")
    parser.add_argument("--time", default=None, help="Время рождения ЧЧ:ММ или пропустить")
    parser.add_argument("--place", required=True, help="Место рождения (город, страна)")
    parser.add_argument("--user", default="debug", help="Имя/идентификатор для файла")
    parser.add_argument("--lat", type=float, help="Явно указать широту (если есть)")
    parser.add_argument("--lng", type=float, help="Явно указать долготу (если есть)")
    parser.add_argument("--tz", help="Явно указать tz (например, Europe/Moscow)")
    args = parser.parse_args()

    if args.lat is not None and args.lng is not None and args.tz:
        result = natal_engine.generate_natal_chart_from_location(
            birth_date=dt.datetime.strptime(args.date, "%d.%m.%Y").date(),
            birth_time=natal_engine.parse_birth_time(args.time),
            lat=args.lat,
            lng=args.lng,
            tz_str=args.tz,
            place_label=args.place,
            user_identifier=args.user,
        )
    else:
        # Для геокодинга потребуется соединение с БД и интернет
        from astro_bot import db  # импорт здесь, чтобы не тянуть его для статичных вызовов

        conn = db.get_connection()
        db.init_db(conn)
        result = natal_engine.generate_natal_chart(
            birth_date_str=args.date,
            birth_time_str=args.time,
            place_query=args.place,
            db_conn=conn,
            user_identifier=args.user,
        )

    print(result.summary)
    print(f"SVG: {result.svg_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
