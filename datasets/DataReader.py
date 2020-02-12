#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@author: Ervin Dervishaj
@email: vindervishaj@gmail.com
'''


import os
import sys
import json
import array
import pickle
import zipfile
import requests
import subprocess
import numpy as np
import pandas as pd
from tqdm import tqdm
import scipy.sparse as sps
from Utils_ import CONSTANTS

import seaborn as sns
import matplotlib.pyplot as plt

class DataReader(object):
    """
    Generic class that implements utilities for datasets
    """

    # MANUALLY SET this taking into account project root
    # datasets_dir = os.path.join(CONSTANTS['root_dir'], 'datasets')
    all_datasets_dir = os.path.dirname(os.path.abspath(__file__))


    def __init__(self,
                 use_cols={'user_id':0, 'item_id':1, 'rating':2},
                 split_ratio=[0.6, 0.2, 0.2],
                 stratified_on='item_popularity',
                 header=False,
                 delim=',',
                 implicit=False,
                 remove_top_pop=0.0,
                 use_local=True,
                 force_rebuild=False,
                 save_local=True,
                 min_ratings=1,
                 verbose=True,
                 seed=1234
                 ):
        """
        Constructor
        """

        super().__init__()

        if sum(split_ratio) != 1.0 or len(split_ratio) != 3:
            raise AttributeError('Split ratio of train, test and validation must sum up to 1')

        self.use_local = use_local
        self.force_rebuild = force_rebuild
        self.save_local = save_local
        self.min_ratings = min_ratings
        self.verbose = verbose

        self.use_cols = use_cols
        self.split_ratio = split_ratio
        self.stratified_on = stratified_on  #TODO: stratification as popularity and considering user/item as class (sklearn-like)
        self.header = header
        self.delimiter = delim
        self.remove_top_pop = remove_top_pop

        if len(use_cols) < 3:
            self.implicit = True
        else:
            self.implicit = implicit


        self.config = {
            'use_cols': self.use_cols,
            'split_ratio': self.split_ratio,
            'stratified_on': self.stratified_on,
            'header': self.header,
            'delim': self.delimiter,
            'implicit': self.implicit,
            'remove_top_pop': self.remove_top_pop,
            'seed': seed
        }


    def build_local(self, ratings_file):
        """
        Builds sparse matrices from ratings file

        Parameters
        ----------
        ratings_file: str
            The full path to the ratings' file

        """
        if os.path.isfile(ratings_file):
            self.URM = self.build_URM(file=ratings_file, use_cols=self.use_cols, delimiter=self.delimiter,
                                      header=self.header, save_local=self.save_local, implicit=self.implicit,
                                      remove_top_pop=self.remove_top_pop, verbose=self.verbose)
            self.URM_train, \
            self.URM_test, \
            self.URM_validation = self.split_urm(self.URM, split_ratio=self.split_ratio, save_local=self.save_local,
                                                 min_ratings=self.min_ratings, verbose=self.verbose,
                                                 save_dir=os.path.dirname(ratings_file))

            try:
                with open(os.path.join(os.path.dirname(ratings_file), 'config.pkl'), 'wb') as f:
                    pickle.dump(self.config, f)
            except AttributeError:
                print('config is not initialized in ' + self.__class__.__name__ + '! No config saved!', file=sys.stderr)

        else:
            print(ratings_file + ' not found. Building remotely...')
            self.build_remote()


    def get_ratings_file(self):
        """
        Downloads the dataset
        """
        zip_file = self.download_url(self.url, self.verbose, desc='Downloading ' + self.DATASET_NAME + ' from ')
        zfile = zipfile.ZipFile(zip_file)
        try:
            self.ratings_file = zfile.extract(self.data_file,
                                os.path.join(self.all_datasets_dir, os.path.dirname(zip_file)))
            # Archive will be deleted
            os.remove(zip_file)
        except (FileNotFoundError, zipfile.BadZipFile):
            print('Either file ' + self.data_file + ' not found or ' + os.path.split(self.url)[-1] + ' is corrupted',
                  file=sys.stderr)
            raise

    
    def build_remote(self):
        """
        Builds sparse matrices
        """
        self.get_ratings_file()
        self.URM = self.build_URM(file=self.ratings_file, use_cols=self.use_cols, delimiter=self.delimiter,
                                    header=self.header, save_local=self.save_local, implicit=self.implicit,
                                    remove_top_pop=self.remove_top_pop, verbose=self.verbose)

        self.URM_train, \
        self.URM_test, \
        self.URM_validation = self.split_urm(self.URM, split_ratio=self.split_ratio, save_local=self.save_local,
                                                min_ratings=self.min_ratings, verbose=self.verbose,
                                                save_dir=os.path.dirname(self.ratings_file))

        try:
            with open(os.path.join(os.path.dirname(self.ratings_file), 'config.pkl'), 'wb') as f:
                pickle.dump(self.config, f)
        except AttributeError:
            print('config is not initialized in ' + self.__class__.__name__ + '!', file=sys.stderr)
            raise


    def download_url(self, url, verbose=True, desc=''):
        """
        Downloads the file found at url.
        To be used to download datasets which are then saved in self.datasets_dir

        Parameters
        ----------
        url: str
            URL where file is located.
        verbose: boolean, default True
            Boolean value whether to show logging
        desc: str
            Description to be used in the download progress bar

        Returns
        -------
        path_to_file: str
            absolute path of the downloaded file from the PROJECT ROOT
        """

        response = requests.get(url, stream=True)
        if response.status_code == 200:
            total_size = 0
            if 'content-length' in response.headers.keys():
                total_size = int(response.headers['content-length'])
            chunk_size = 1024 * 4

            filename = url.split('/')[-1]
            abs_path = os.path.join(self.all_datasets_dir,  self.dataset_dir, filename)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)

            pbar = tqdm(total=total_size, desc=desc+url, unit='B', unit_scale=True, unit_divisor=1024, disable=not verbose and total_size != 0)

            with open(abs_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(chunk_size)
                pbar.close()
            return abs_path

        else:
            raise requests.HTTPError('Request for download returned with status ' + response.status_code)


    def download_kaggle_dataset(self, dataset, files='all', verbose=True):
        """
        Downloads a dataset from Kaggle as specified by parameter dataset.
        Please set username and Kaggle API key in ~/.kaggle/kaggle.json.

        :param dataset: Name of the dataset as specified by Kaggle of the format <owner>/<dataset-name>.
                Can be searched by running `kaggle datasets list -s DATASET_NAME`
        :param files: Name of the file to download. Can be found by running `kaggle datasets files DATASET_NAME`.
                If `all` then all the files of the dataset will be downloaded
        :param verbose: Default True
        """


        # By default kaggle.json should reside within ~/.kaggle
        kaggle_filepath = os.path.expanduser('~/.kaggle/kaggle.json')

        # If kaggle.json does not exist
        if not os.path.exists(kaggle_filepath):
            raise IOError('File kaggle.json not found in ~/.kaggle. Please place it there and rerun.')

            # Create it and store it
            # if self.defs.username is None and self.defs.key is None:
            #     raise ValueError('Credentials must be provided either through kaggle.json or username and key in order to download datasets from Kaggle.com.')

            # else:
            #     if verbose:
            #         print(kaggle_filepath + ' missing. Using hardcoded username and key from Utils.py to create it.')
            #     kaggle_dict = {}
            #     kaggle_dict['username'] = self.defs.username
            #     kaggle_dict['key'] = self.defs.key
            #     os.makedirs(os.path.dirname(kaggle_filepath), exist_ok=True)
            #     with open(kaggle_filepath, 'w') as f:
            #         json.dump(kaggle_dict, f)
            #     subprocess.run(['chmod', '600', kaggle_filepath])

        # First create a folder inside datasets with the name of the dataset (without the <owner> part)
        dataset_path = os.path.join(self.all_datasets_dir, dataset.split('/')[-1])
        os.makedirs(dataset_path, exist_ok=True)

        # kaggle is installed in bin folder where python is
        kaggle_cmdpath = os.path.join(os.path.dirname(sys.executable), 'kaggle')

        # Run kaggle command through subprocess
        if files == 'all':
            subprocess.run([kaggle_cmdpath, 'datasets', 'download', dataset, '-p', dataset_path, '--force'])
        elif isinstance(files, list):
            for f in files:
                subprocess.run([kaggle_cmdpath, 'datasets', 'download', dataset, '-p', dataset_path, '--force', '-f', f])
        elif isinstance(files, str):
            subprocess.run([kaggle_cmdpath, 'datasets', 'download', dataset, '-p', dataset_path, '--force', '-f', files])
        else:
            raise ValueError('files argument accepts either `all`, a single filename or a list of filenames.')

        # Unzip all files downloaded and delete zip files
        if verbose:
            print('Extracting downloaded files. Archive files will be removed.')
        for filename in os.listdir(dataset_path):
            fpath = os.path.join(dataset_path, filename)
            if os.path.isfile(fpath) and os.path.splitext(filename)[1] == '.zip':
                zfile = zipfile.ZipFile(fpath)
                zfile.extractall(path=dataset_path)
                os.remove(fpath)
        #TODO: need to find a fast way to merge all files downloaded


    def read_interactions(self,
                          file,
                          use_cols={'user_id': 0, 'item_id': 1, 'rating': 2},
                          delimiter=',',
                          header=False,
                          verbose=True):
        """
        Reads the interactions data file and fills the rows, columns and data arrays

        Parameters
        ----------
        file: str
            Absolute/relative path from the project root to the file with the ratings.

        use_cols: dict, default {'user_id':0, 'item_id':1, 'rating':2}
            Columns to be used from the file as dict. DO NOT change dict keys.

        delimiter: str, default `,`
            Delimiter of the file.

        header: boolean, default False
            Flag indicating whether ratings' file has a header.
        
        Returns:
        --------
        rows: array.array
        cols: array.array
        data: array.array
        """

        rows = array.array('I')
        cols = array.array('I')
        data = array.array('f')

        with open(file, 'r') as f:

            if header:
                f.readline()

            if verbose:
                print('Filling the full URM...')

            # # Netflix Dataset requires preprocessing and it's big so
            # # it is better to generate the matrices in one reading
            # if netflix_process:
            #     current_item_id = -1

            #     for line in f:
            #         row_data = line.split(delimiter)

            #         if len(row_data) == 1:
            #             # This is an item id
            #             current_item_id = int(row_data[0][:-2])
            #         else:
            #             rows.append(int(row_data[0]))
            #             data.append(int(row_data[1]))
            #             cols.append(current_item_id)

            # else:
            for line in f:
                row_data = line.split(delimiter)
                rows.append(int(row_data[use_cols['user_id']]))
                cols.append(int(row_data[use_cols['item_id']]))
                data.append(float(row_data[use_cols['rating']]))

        return rows, cols, data
    
    
    def build_URM(self,
                  file,
                  use_cols={'user_id': 0, 'item_id': 1, 'rating': 2},
                  delimiter=',',
                  header=False,
                  save_local=True,
                  implicit=False,
                  remove_top_pop=0.0,
                  verbose=True):
        """
        Builds the URM from interactions data file.

        Parameters
        ----------
        file: str
            Absolute/relative path from the project root to the file with the ratings.

        use_cols: dict, default {'user_id':0, 'item_id':1, 'rating':2}
            Columns to be used from the file as dict. DO NOT change dict keys.

        delimiter: str, default `,`
            Delimiter of the file.

        header: boolean, default False
            Flag indicating whether ratings' file has a header.

        save_local: boolean, default True
            Flag indicating whether the URM should be saved locally.

        implicit: boolean, default False
            Flag indicating whether the ratings should be implicit. If True the column of ratings is substituted with ones.

        remove_top_pop: float, default 0.0
            Fraction of most popular items to be removed from the final URM.

        verbose: boolean, default True
            Flag indicating whether logging should be printed out.


        Returns
        -------
        URM: scipy.sparse.coo_matrix
            The full URM in COO format.
        """

        rows, cols, data = self.read_interactions(file, use_cols, delimiter, header, verbose)

        if implicit:
            data = np.ones(len(data))

        unique_items, item_counts = np.unique(cols, return_counts=True)

        if remove_top_pop > 0.0:
            k = int(np.floor(len(unique_items) * remove_top_pop))
            sorted_indices = np.argsort(item_counts)[::-1]
            unique_items = unique_items[sorted_indices][k:]
            col_mask = np.isin(cols, unique_items)
            cols = np.frombuffer(cols, dtype=np.int32)[col_mask]
            rows = np.frombuffer(rows, dtype=np.int32)[col_mask]
            if not isinstance(data, np.ndarray):
                data = np.frombuffer(data, dtype=np.float32)[col_mask]
            else:
                data = data[col_mask]

        unique_users = np.unique(rows)

        shape = (len(unique_users), len(unique_items))

        self.row_to_user = dict(zip(unique_users, range(0, len(unique_users))))
        self.col_to_item = dict(zip(unique_items, range(0, len(unique_items))))

        coo_rows = pd.Series(rows).map(self.row_to_user).values
        coo_cols = pd.Series(cols).map(self.col_to_item).values

        self.URM = sps.coo_matrix((data, (coo_rows, coo_cols)), shape=shape, dtype=np.float32)

        if save_local:
            if verbose:
                print('Saving full URM locally...')

            sps.save_npz(os.path.join(os.path.dirname(file), 'URM'), self.URM, compressed=True)
            np.save(os.path.join(os.path.dirname(file), 'row_to_user'), self.row_to_user, allow_pickle=True)
            np.save(os.path.join(os.path.dirname(file), 'col_to_item'), self.col_to_item, allow_pickle=True)

        # Delete arrays to save space
        data, rows, cols = None, None, None

        return self.URM
    
    
    def split_urm(self, URM=None, split_ratio=[0.6, 0.2, 0.2], save_local=True, min_ratings=1, verbose=True, save_dir=None):
        """
        Creates sparse matrices from full URM.

        Parameters
        ----------
        URM: scipy.sparse.coo_matrix
            The full URM in COO format.

        split_ratio: array-like, default [0.6, 0.2, 0.2]
            Train-Test-Validation split ratio. Must sum to 1.

        save_local: boolean, default True
            Flag indicating whether to save the resulting sparse matrices locally.

        min_ratings: int, default 1
            Number of ratings that each user must have in order to be included in any of the splits.

        verbose: boolean, default True
            Flag indicating whether to print logging.

        save_dir: str, default None
            Directory where to save the sparse matrices.


        Returns
        -------
        URM_train: scipy.sparse.csr_matrix
            URM in CSR format to be used for training.

        URM_test: scipy.sparse.csr_matrix
            URM in CSR format to be used for testing.

        URM_validation: scipy.sparse.csr_matrix
            URM in CSR format to be used for validation.

        """

        if URM is None:
            try:
                URM = self.URM
            except AttributeError:
                print('URM is not initialized in ' + self.__class__.__name__ + '!', file=sys.stderr)
                raise

        if min_ratings != 1: #TODO: this should be bypassed if self.implicit == True
            if verbose:
                print('Removing ratings of users with less than ' + min_ratings + ' ratings...')

            URM_csr = sps.csr_matrix(URM)
            user_mask = (URM_csr.sum(axis=1).A1 < min_ratings).nonzero()[0]
            URM = sps.lil_matrix(URM_csr)
            URM[user_mask,:] = 0.0
            URM = URM.tocsr()
            URM.eliminate_zeros()
            URM = URM.tocoo()

        if verbose:
            print('Splitting the full URM into train, test and validation matrices...')

        choice = np.random.choice(['train', 'test', 'valid'], p=split_ratio, size=len(URM.data))

        shape = URM.shape
        URM_train = sps.coo_matrix((URM.data[choice == 'train'], (URM.row[choice == 'train'], URM.col[choice == 'train'])), shape=shape, dtype=np.float32)
        URM_test = sps.coo_matrix((URM.data[choice == 'test'], (URM.row[choice == 'test'], URM.col[choice == 'test'])), shape=shape, dtype=np.float32)
        URM_validation = sps.coo_matrix((URM.data[choice == 'valid'], (URM.row[choice == 'valid'], URM.col[choice == 'valid'])), shape=shape, dtype=np.float32)

        self.URM_train = URM_train.tocsr()
        self.URM_test = URM_test.tocsr()
        self.URM_validation = URM_validation.tocsr()

        if save_local and save_dir is not None:
            if verbose:
                print('Saving matrices locally...')

            sps.save_npz(os.path.join(save_dir, 'URM_train'), self.URM_train, compressed=True)
            sps.save_npz(os.path.join(save_dir, 'URM_test'), self.URM_test, compressed=True)
            sps.save_npz(os.path.join(save_dir, 'URM_validation'), self.URM_validation, compressed=True)

        return self.URM_train, self.URM_test, self.URM_validation


    def get_CV_folds(self, URM=None, folds=10, verbose=True):
        """
        Generator function implementing cross-validation from interactions data file.

        :param URM: URM to use for generating the folds. If None, the attribute URM of the class will be used.
        :param folds: Number of CV folds
        :param verbose: True to print logging

        Yields train and test matrices in CSR format
        """

        if verbose:
            print('Generating train and test folds...')

        if URM is None:
            try:
                URM = self.URM
            except AttributeError:
                print('URM is not initialized in ' + self.__class__.__name__ + '!', file=sys.stderr)
                raise

        choice = np.random.choice(range(folds), size=len(URM.data))
        shape = URM.shape
        for i in range(folds):
            URM_test = sps.coo_matrix((URM.data[choice == i], (URM.row[choice == i], URM.col[choice == i])), shape=shape, dtype=np.float32)
            URM_train = sps.coo_matrix((URM.data[choice != i], (URM.row[choice != i], URM.col[choice != i])), shape=shape, dtype=np.float32)
            yield URM_train.tocsr(), URM_test.tocsr()


    def get_URM_full(self, transposed=False):
        try:
            if transposed:
                return self.URM.T
            else:
                return self.URM
        except AttributeError:
            print('URM is not initialized in ' + self.__class__.__name__ + '!', file=sys.stderr)
            raise


    def get_URM_train(self, transposed=False):
        try:
            if transposed:
                return self.URM_train.T.tocsr()
            return self.URM_train
        except AttributeError:
            print('URM_train is not initialized in ' + self.__class__.__name__ + '!')
            raise


    def get_URM_test(self, transposed=False):
        try:
            if transposed:
                return self.URM_test.T.tocsr()
            return self.URM_test
        except AttributeError:
            print('URM_test is not initialized in ' + self.__class__.__name__ + '!', file=sys.stderr)
            raise


    def get_URM_validation(self, transposed=False):
        try:
            if transposed:
                return self.URM_validation.T.tocsr()
            return self.URM_validation
        except AttributeError:
            print('URM_validation is not initialized in ' + self.__class__.__name__ + '!', file=sys.stderr)
            raise


    def process(self):
        """
        Read prebuild sparse matrices or generate them from ratings file.
        """

        # Check if files URM_train, URM_test and URM_validation OR URM already exists first
        # If not, build locally the sparse matrices using the ratings' file

        if self.use_local:
            ratings_file = os.path.join(self.all_datasets_dir, self.dataset_dir, self.data_file)
            self.matrices_path = os.path.join(self.all_datasets_dir, os.path.dirname(ratings_file))

            train_path = os.path.join(self.matrices_path, 'URM_train.npz')
            test_path = os.path.join(self.matrices_path, 'URM_test.npz')
            valid_path = os.path.join(self.matrices_path, 'URM_validation.npz')
            urm_path = os.path.join(self.matrices_path, 'URM.npz')

            # Read the build config and compare with current build
            config_path = os.path.join(self.matrices_path, 'config.pkl')
            if os.path.isfile(config_path):
                with open(config_path, 'rb') as f:
                    config = pickle.load(f)

                try:
                    if self.config != config:
                        if self.verbose:
                            print('Local matrices built differently from requested build. Setting force_rebuild = True.')
                        self.force_rebuild = True
                except AttributeError:
                    print('config is not initialized in ' + self.__class__.__name__ + '!', file=sys.stderr)
                    self.force_rebuild = True

            else:
                if self.verbose:
                    print('Configuration file not found. Setting force_rebuild = True.')
                self.force_rebuild = True

            if not self.force_rebuild:
                if os.path.isfile(train_path) and os.path.isfile(test_path) and os.path.isfile(valid_path):
                    if self.verbose:
                        print('Loading train, test and validation matrices locally...')

                    self.URM_train = sps.load_npz(train_path)
                    self.URM_test = sps.load_npz(test_path)
                    self.URM_validation = sps.load_npz(valid_path)

                    if os.path.isfile(urm_path):
                        self.URM = sps.load_npz(urm_path)

                elif os.path.isfile(urm_path):
                    if self.verbose:
                        print('Building from full URM...')

                    self.URM = sps.load_npz(urm_path)

                    self.URM_train, \
                    self.URM_test, \
                    self.URM_validation = self.split_urm(self.URM, split_ratio=self.split_ratio,
                                                         save_local=self.save_local, min_ratings=self.min_ratings,
                                                         verbose=self.verbose, save_dir=os.path.dirname(urm_path))
                else:
                    if self.verbose:
                        print("Matrices not found. Building from ratings' file...")

                    if os.path.exists(ratings_file):
                        self.build_local(ratings_file)
                    else:
                        self.build_remote()

            else:
                if self.verbose:
                    print("Rebuilding asked. Building from ratings' file...")

                if os.path.exists(ratings_file):
                    self.build_local(ratings_file)
                else:
                    self.build_remote()

        # Either remote building asked or ratings' file is missing
        else:
            self.build_remote()


    def describe(self, save_plots=False):
        """
        Describes the full URM
        """

        try:
            # The URM is assumed to have shape users x items
            no_users = self.URM.shape[0]
            no_items = self.URM.shape[1]
            ratings = self.URM.nnz
            density = ratings / no_users / no_items
            items_per_user = self.URM.sum(axis=1).A1
            users_per_item = self.URM.sum(axis=0).A1
            cold_start_users = int(np.sum(np.where(items_per_user == 0)))
            mean_item_per_user = int(np.round(np.mean(items_per_user)))
            min_item_per_user = int(np.min(items_per_user))
            max_item_per_user = int(np.max(items_per_user))

            print('Users: {:d}\nItems: {:d}\nRatings: {:d}\nDensity: {:.5f}%\nCold start users: {:d}\n'
                    'Minimum items per user: {:d}\nMaximum items per user: {:d}\nAvg.items per user: {:d}'
                  .format(no_users, no_items, ratings, density*100, cold_start_users, min_item_per_user, max_item_per_user, mean_item_per_user))

            sns.set_style('darkgrid')

            fig1, ax1 = plt.subplots()
            sns.distplot(items_per_user, rug=False, kde=False, label='count_users', axlabel='interactions', ax=ax1)
            ax1.set_ylabel('count_users')

            fig2, ax2 = plt.subplots()
            sns.distplot(users_per_item, rug=False, kde=False, label='count_items', axlabel='interactions', ax=ax2)
            ax2.set_ylabel('count_items')

            if save_plots:
                fig1.savefig(os.path.join(self.matrices_path, 'user_interaction_distr.png'), bbox_inches="tight")
                fig2.savefig(os.path.join(self.matrices_path, 'item_interaction_distr.png'), bbox_inches="tight")
            else:
                plt.show()
        except AttributeError:
            print('URM is not initialized in ' + self.__class__.__name__ + '!', file=sys.stderr)
            raise