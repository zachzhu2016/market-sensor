import os, math
from multiprocessing import Pool
from pyspark.sql import SparkSession
from collections import Counter
from datetime import timedelta
import stanza
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd 
from tqdm import tqdm
import dask.dataframe as dd
from dask.multiprocessing import get

from instrument import * 
from article import *

class AnalyticEngine:
    def __init__(self, symbol_map, startdate, enddate, interval, spark: SparkSession, data_dir='./data'):
        self.symbol_map = symbol_map
        self.startdate = startdate
        self.enddate = enddate
        self.interval = interval
        self.instruments = list()
        self.histories = list()
        self.data = dict()
        self.data_dir = data_dir
        self.source_df = None
        self.spark = spark
    
    def graph(self, symbols, window=7):
        self.score_and_predict(symbols, window=window)
        for symbol in symbols:
            fig, axes = plt.subplots(2)
            df_dict = self.data[symbol]
            price_series = df_dict['timeline_df']['open'].plot.line(ax=axes[0])
            title_sentiment_series = df_dict['timeline_df']['title_score'].plot.line(ax=axes[1])
            text_sentiment_series = df_dict['timeline_df']['text_score'].plot.line(ax=axes[1])
            plt.legend()
            plt.show()

    def analyze_sentiment_distribution(self, symbols, window=7, info='', save_fig=False, show_fig=False):
        title_scores = []
        text_scores = []
        for symbol in symbols: 
            timeline_df = self.data[symbol]['timeline_df']


    def analyze_accuracy(self, symbols, window=7, info='', save_fig=False, show_fig=False):
        '''
        analyze accuracies for each symbol given a window length
        '''
        def safe_divide(a, b):
            if b == 0:
                return 0
            return a / b

        res = dict()
        self.score_and_predict(symbols, window=window)
        for symbol in symbols:
            res[symbol] = dict()
            timeline_df = self.data[symbol]['timeline_df']

            title_pos_correct = timeline_df[(timeline_df['title_prediction'] == 'buy') & (timeline_df['title_result'] == 1)].shape[0]
            title_neg_correct = timeline_df[(timeline_df['title_prediction'] == 'sell') & (timeline_df['title_result'] == 1)].shape[0]
            title_hold_correct = timeline_df[(timeline_df['title_prediction'] == 'hold') & (timeline_df['title_result'] == 1)].shape[0]
            title_correct = title_pos_correct + title_neg_correct + title_hold_correct

            text_pos_correct = timeline_df[(timeline_df['text_prediction'] == 'buy') & (timeline_df['text_result'] == 1)].shape[0]
            text_neg_correct = timeline_df[(timeline_df['text_prediction'] == 'sell') & (timeline_df['text_result'] == 1)].shape[0]
            text_hold_correct = timeline_df[(timeline_df['text_prediction'] == 'hold') & (timeline_df['text_result'] == 1)].shape[0]
            text_correct = text_pos_correct + text_neg_correct + text_hold_correct

            res[symbol]['title_pos_accuracy'] = safe_divide(title_pos_correct, timeline_df[timeline_df['title_prediction'] == 'buy'].shape[0])
            res[symbol]['title_neg_accuracy'] = safe_divide(title_neg_correct, timeline_df[timeline_df['title_prediction'] == 'sell'].shape[0])
            res[symbol]['title_hold_accuracy'] = safe_divide(title_hold_correct, timeline_df[timeline_df['title_prediction'] == 'hold'].shape[0])
            res[symbol]['title_accuracy'] = safe_divide(title_correct, timeline_df[timeline_df['title_prediction'] != ''].shape[0])
            res[symbol]['text_pos_accuracy'] = safe_divide(text_pos_correct, timeline_df[timeline_df['text_prediction'] == 'buy'].shape[0])
            res[symbol]['text_neg_accuracy'] = safe_divide(text_neg_correct, timeline_df[timeline_df['text_prediction'] == 'sell'].shape[0])
            res[symbol]['text_hold_accuracy'] = safe_divide(text_hold_correct, timeline_df[timeline_df['text_prediction'] == 'hold'].shape[0])
            res[symbol]['text_accuracy'] = safe_divide(text_correct, timeline_df[timeline_df['text_prediction'] != ''].shape[0])

        print(res)
        for accuracy in ['title_pos_accuracy', 'title_neg_accuracy', 'title_hold_accuracy', 'title_accuracy', 'text_pos_accuracy', 'text_neg_accuracy', 'text_hold_accuracy', 'text_accuracy']:
            plt.bar(symbols, [res[symbol][accuracy] for symbol in symbols], label=accuracy)

        plt.ylabel('accuracy % / 100')
        plt.legend()
        if save_fig:
            plt.savefig(f'./chart/accuracy_{window}.jpg')
        if show_fig:
            plt.show()
        plt.clf()

        print('=> output of analyze_accuracy')
        print(res)
        return res

    def analyze_accuracies(self, windows, save_fig=False, show_fig=False):
        '''
        analyze accuracies for each industry for each window length
        '''
        res_list = list()
        for industry, symbols in self.symbol_map.items():
            res = dict()
            for window in windows:
                subres = self.analyze_accuracy(symbols, window=window, info=f'window={window}')
                res[window] = dict()
                for accuracy in ['title_pos_accuracy', 'title_neg_accuracy', 'title_hold_accuracy', 'title_accuracy', 'text_pos_accuracy', 'text_neg_accuracy', 'text_hold_accuracy', 'text_accuracy']:
                    res[window][accuracy] = sum([subres[symbol][accuracy] for symbol in subres]) / len(subres)

            for accuracy in ['title_pos_accuracy', 'title_neg_accuracy', 'title_hold_accuracy', 'title_accuracy', 'text_pos_accuracy', 'text_neg_accuracy', 'text_hold_accuracy', 'text_accuracy']:
                plt.plot(windows, [res[window][accuracy] for window in windows], label=accuracy)

            plt.ylabel('accuracy % / 100')
            plt.xlabel('Window in days')
            plt.legend()
            if save_fig:
                plt.savefig(f'./chart/accuracies_{industry}.jpg')
            if show_fig:
                plt.show()
            plt.clf()
            res_list.append(res)

        print('=> output of analyze_accuracies')
        print(res_list)
        return res_list
    
    def analyze_cov(self, symbols, window=7, info='', save_fig=False, show_fig=False):
        '''
        analyze covariance for each symbol given a window length
        '''
        res = dict()
        res['price_title'] = []
        res['price_text'] = []
        res['title_text'] = []
        self.score_and_predict(symbols, window=window)
        for symbol in symbols:
            df_dict = self.data[symbol]
            res['price_title'].append((df_dict['timeline_df']['change'] * 10).cov(df_dict['timeline_df']['title_score']))
            res['price_text'].append((df_dict['timeline_df']['change'] * 10).cov(df_dict['timeline_df']['text_score']))
            res['title_text'].append((df_dict['timeline_df']['title_score'] * 10).cov(df_dict['timeline_df']['text_score']))

        plt.bar(symbols, res['price_title'], label='price change and title_score covariance')
        plt.bar(symbols, res['price_text'], label='price change and text_score covariance')
        plt.bar(symbols, res['title_text'], label='title_score and text_score covariance')
        plt.title(f'Covariance Analysis: window={window}, info={info}')
        plt.ylabel('Covariance Normalized by N-1 (Unbiased Estimator)')
        plt.legend()
        if save_fig:
            plt.savefig(f'./chart/cov_{window}.jpg')
        if show_fig:
            plt.show()
        plt.clf()

        print('=> output of analyze_cov')
        print(res)
        return res

    def analyze_covs(self, windows, save_fig=False, show_fig=False):
        '''
        analyze covariance for each industry for each window length
        '''
        res_list = list()
        for industry, symbols in self.symbol_map.items():
            res = dict()
            for window in windows:
                covs = self.analyze_cov(symbols, window=window, info='for all symbols')
                res[window] = dict()
                for k in covs:
                    res[window][k] = sum(covs[k])
            
            for k in ['price_text', 'price_title', 'title_text']: 
                plt.plot(windows, [res[window][k] for window in windows], label=k)

            plt.ylabel(f'Covariance Sum for {len(windows)} window days')
            plt.xlabel('Window in Days')
            plt.legend()
            if save_fig:
                plt.savefig(f'./chart/covs_{industry}.jpg')
            if show_fig:
                plt.show()
            plt.clf()
            res_list.append(res)

        print('=> output of analyze_covs')
        print(res_list)
        return res_list

    def calc_score(self, currdate, article_df_col, article_df, timeline_df, window):
        average = lambda scores: sum(scores) / len(scores) if len(scores) > 0 else None
        article_count = 0
        scores = []
        days = [max(window - 3, 0), max(window - 2, 0), max(window - 1, 0), window, window + 1, window + 2, window + 3] 
        # days = list(range(window))
        for i, day in enumerate(days):
            article_links = None
            try:
                article_links = timeline_df.loc[currdate - timedelta(days=day)]['links']
            except KeyError:
                continue

            if not article_links:
                continue

            for link in article_links:
                try:
                    article = article_df.loc[link]
                    sentiment = article[article_df_col]
                    source_url = article['source']['href']
                    score = sentiment 
                except:
                    continue
                scores.append(score)

            article_count += len(article_links)
        
        timeline_df.at[currdate, 'article_count'] = article_count
        final_score = average(scores) 
        return final_score

    def predict(self, score):
        if not score:
            return ''
        if 45 < score < 55:
            return 'hold'
        elif score > 55:
            return 'buy'
        elif score < 45:
            return 'sell'
        else:
            return ''

    def calc_accuracy(self, prediction, change):
        if not prediction:
            return -1 
        if prediction == 'hold' and abs(change) < 0.25:
            return 1
        elif prediction == 'buy' and change > 0.25:
            return 1 
        elif prediction == 'sell' and change < -0.25:
            return 1
        else: 
            return 0


    def score_and_predict(self, symbols, window=7):
        '''
        parallelize this function / use spark
        '''
        print('=> adding scores and calculating accuracies:')
        for symbol in tqdm(symbols):
            df_dict = self.data[symbol]
            article_df = df_dict['article_df']
            timeline_df = df_dict['timeline_df']
            if all([timeline_df.empty, article_df.empty]):
                continue

            timeline_df['article_count'] = None
            timeline_df['title_score'] = timeline_df.index.map(lambda index: self.calc_score(index, 'title_sentiment', article_df, timeline_df, window))
            timeline_df['text_score'] = timeline_df.index.map(lambda index: self.calc_score(index, 'text_sentiment', article_df, timeline_df, window))

            timeline_df = self.fill_score(timeline_df) 
            
            timeline_df['title_prediction'] = timeline_df.apply(lambda row: self.predict(row['title_score']), axis=1)
            timeline_df['text_prediction'] = timeline_df.apply(lambda row: self.predict(row['text_score']), axis=1)
            
            timeline_df['title_result'] = timeline_df.apply(lambda row: self.calc_accuracy(row['title_prediction'], row['change']), axis=1)
            timeline_df['text_result'] = timeline_df.apply(lambda row: self.calc_accuracy(row['text_prediction'], row['change']), axis=1)
            df_dict['timeline_df'] = timeline_df

    def fill_score(self, timeline_df, limit = 3):
        '''
        fills scores from previous days if not available
        '''
        delay = timedelta(days=0)
        for currdate, row in timeline_df.iterrows():
            try:
                # attempt to use previous score
                while delay.days < limit and (pd.isna(timeline_df.at[currdate, 'title_score']) or pd.isna(timeline_df.at[currdate, 'text_score'])):
                    if pd.isna(timeline_df.at[currdate, 'title_score']) and not pd.isna(timeline_df.at[currdate - delay, 'title_score']):
                        timeline_df.at[currdate, 'title_score'] = timeline_df.at[currdate - delay, 'title_score']
                    if pd.isna(timeline_df.at[currdate, 'text_score']) and not pd.isna(timeline_df.at[currdate - delay, 'text_score']):
                        timeline_df.at[currdate, 'text_score'] = timeline_df.at[currdate - delay, 'text_score']
                    delay += timedelta(days=1)
                # use neutral score
                timeline_df['title_score'].replace({np.nan: 50}, inplace=True)
                timeline_df['text_score'].replace({np.nan: 50}, inplace=True)
            except Exception as e:
                continue
        return timeline_df

    def sample_article_dfs(self, save=True):
        article_dfs = [df_dict['article_df'].sample(n=10) for df_dict in self.data.values()]
        sample_df = pd.concat(article_dfs)
        if save:
            dest = f'./data/sample.csv'
            sample_df.to_csv(dest)
            print(f'saving sampled article dataframes to "{dest}"')
        return sample_df
        
    def load_all(self):
        ''' 
        load cached dataframes
        '''

        self.load_instruments()
        self.load_histories(self.instruments)
        self.load_data(from_cache=True)
        self.load_source_df()

    def load_instruments(self):
        self.instruments = Instrument.load_instruments(self.symbol_map, self.startdate, self.enddate)

    def load_histories(self, instruments, download_article_content=False):
        '''
        load cached ArticleHistory objects
        '''

        for instrument in instruments:
            startdate, enddate = instrument.date_range()
            if not all([startdate, enddate]):
                continue

            history = ArticleHistory.load_history(instrument, startdate, enddate, self.interval)
            if download_article_content:
                history.download_text()

            self.histories.append(history)

    def load_source_df(self):
        '''
        creates a source-article-count dataframe 
        '''

        article_dfs = [df_dict['article_df'] for df_dict in self.data.values()]
        source_urls = list()
        for article_df in article_dfs:
            source_urls += article_df['source'].apply(lambda source: source['href']).tolist()
        source_count = Counter(source_urls)
        total = sum(source_count.values())
        source_dict = {url: ((count + total) / total) for url, count in source_count.items()}
        self.source_df = pd.DataFrame.from_dict(source_dict, orient='index', columns=['weight'])

    def load_data(self, from_cache=True):
        if from_cache:
            for objname in cache.listcache(f'{AnalyticEngine.__name__}'):
                symbol, df_name = objname.split('-')[1:]
                if symbol not in self.data:
                    self.data[symbol] = dict()
                self.data[symbol][df_name] = cache.readcache(objname)
        else:
            self.add_all()


    def cache_data(self):
        for symbol, df_dict in tqdm(self.data.items()):
            for df_name, df in df_dict.items():
                cache.writecache(f'{AnalyticEngine.__name__}-{symbol}-{df_name}', df)

    def add_all(self):
        ''' 
        create dataframes from cached objects
        '''

        self.load_instruments()
        self.load_histories(self.instruments)
        self.add_data()

    def add_data(self):
        ''' 
        creates dataframes from objects in cache
        '''

        for instrument, history in zip(self.instruments, self.histories):
            articles = history.get_aligned_articles()
            articles_dict = dict()
            columns = ['published', 'title', 'link', 'source', 'id', 'text', 'title_sentiment', 'text_sentiment']
            for col in columns:
                articles_dict[col] = []
                for article in articles:
                    articles_dict[col].append(article.get(col))

            article_df = pd.DataFrame.from_dict(articles_dict).set_index('link', drop=False, verify_integrity=True)
            article_series = article_df.groupby('published')['link'].apply(list).rename('links')
            timeline_df = pd.merge(instrument.df, article_series, left_index=True, right_index=True, how='left')
            timeline_df = timeline_df[['Open', 'Close', 'links']].replace({np.nan: None})
            timeline_df = timeline_df.rename(columns={'Date': 'date', 'Open': 'open', 'Close': 'close'})
            timeline_df['change'] = timeline_df.apply(lambda row: 100 * (row['close'] - row['open']) / row['open'], axis=1)
            timeline_df.index = pd.to_datetime(timeline_df.index)

            timeline_df.name = instrument.id
            article_df.name = instrument.id
    
            self.data[instrument.id] = dict()
            self.data[instrument.id]['timeline_df'] = timeline_df
            self.data[instrument.id]['article_df'] = article_df

    def __repr__(self):
        return f'AnalyticEngine(data={len(self.data)}, histories={len(self.histories)})'

