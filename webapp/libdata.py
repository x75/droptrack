import pandas as pd
import numpy as np

def data_init(columns=[], filename=None):
    df = None
    if filename is not None:
        try:
            df = pd.read_csv(filename)
            print(f'    {__name__} data_init df loaded from {filename}\n{df}')
        except Exception as e:
            print(f'    {__name__} data_init load file exception {e}')

    if df is None:
        df = pd.DataFrame(columns=columns)
        print(f'    {__name__} data_init df created {df}')
        
    df.to_csv(filename, index=False)
    return df

def data_get_columns(df):
    return df.columns

def data_append_row(data, df):
    df = df.append(data, ignore_index=True)
    return df

def data_write(df, filename):
    df.to_csv(filename, index=False)

if __name__ == '__main__':
    print(__name__)

    df = data_init(['id', 'name', 'length'], 'libdata-df-test.csv')

    print(f'{__name__} main df {df}')

    dfcols = data_get_columns(df)

    print(f'{__name__} main dfcols {dfcols}')


    names = ['asdsad', 'fgdfd', 'wer23r', 'dgkmk', 'r439k']
    lengths = np.random.randint(1, 10, (5,))
    for i in range(5):
        row = [i, names[i], lengths[i]]
        rowdict = dict(zip(dfcols, row))
        print(f'{__name__} main appending row {row}')
        df = data_append_row(rowdict, df)

    print(f'{__name__} main post append df {df}')

    data_write(df, 'libdata-df-test-filled.csv')
