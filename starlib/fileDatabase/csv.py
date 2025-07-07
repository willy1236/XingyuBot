import csv
import os
from typing import TYPE_CHECKING

import pandas as pd


class CsvDatabase:
    if TYPE_CHECKING:
        lol_champion: pd.DataFrame

    def __init__(self):
        self._db_location = "./database"
        self._filepath = {"lol_champion": f"{self._db_location}/lol_champion.csv"}

        if not os.path.isdir(self._db_location):
            os.mkdir(self._db_location)

        for file in self._filepath:
            if os.path.isfile(self._filepath[file]):
                setattr(self, file, pd.read_csv(open(self._filepath[file], mode="r", encoding="utf8")))
            else:
                print(f"Missing file: {self._filepath[file]}")

    def read_data_to_list(self, path):
        with open(f"{path}.csv", "r") as csvfile:
            csvReader = csv.reader(csvfile)
            data = list(csvReader)
        for row in data:
            print(row)
        return data

    def read_data_to_dict_reader(self, path):
        with open(f"{path}.csv", "r") as csvfile:
            csvReader = csv.DictReader(csvfile)
        for row in csvReader:
            print(row)
        return csvReader

    def write_data(self, path, data: list):
        with open(f"{path}.csv", "r", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(data)

    def write_data_with_dict_writer(self, path, field: list, data: dict):
        with open(f"{path}.csv", "r", newline="") as csvfile:
            dictWriter = csv.DictWriter(csvfile, fieldnames=field)
            dictWriter.writeheader()
            dictWriter.writerow(data)

    @staticmethod
    def find_row_by_column_value(file_path, column_name, target_value):
        df = pd.read_csv(file_path)
        row = df[df[column_name] == target_value]
        if not row.empty:
            return row.iloc[0]  # Return the first matching row
        return None

    def get_row(self, df: pd.DataFrame, colume: str, value) -> pd.Series:
        """給予指定欄位與其值，尋找符合的資料
        :param df: 要尋找的資料表
        :param colume: 尋找資料的條件欄位
        :param value: 尋找資料的條件值
        """
        row = df[df[colume] == value]
        if not row.empty:
            return row.iloc[0]
        return pd.Series()
