import pandas as pd
from pathlib import Path
#from ydata_profiling import ProfileReport
import re
import contractions
import emoji
import nltk
from nltk.corpus import stopwords, words
from nltk.stem import WordNetLemmatizer
from vocabulary import *
import pandas as pd
from nltk.stem import WordNetLemmatizer
from nltk import pos_tag, word_tokenize
from nltk.corpus import wordnet
nltk.download('averaged_perceptron_tagger')
nltk.download('wordnet')
import wordninja
from symspellpy import SymSpell
import pkg_resources
from tqdm import tqdm

nltk.download('stopwords')
nltk.download('words')
common = words.words()
sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
dictionary_path = pkg_resources.resource_filename("symspellpy", "frequency_dictionary_en_82_765.txt")
sym_spell.load_dictionary(dictionary_path, term_index=0, count_index=1)
tqdm.pandas()


class DataProcessor:
    def __init__(self, dataset_type, prj_dir, train_files, test_file, preprocessing_policy):
        self.dataset_type = dataset_type
        self.prj_dir = prj_dir
        self.train_files = train_files
        self.test_file = test_file
        self.preprocessing_policy = preprocessing_policy
    
    def load_data(self, is_test=False):
        if is_test:
            df = pd.DataFrame()
            with open(self.test_file, 'r', encoding='utf-8') as file:
                data = [line.split(',', 1) for line in file.readlines()]
            df = pd.DataFrame(data, columns=["id", "tweet"])
            return df
        else:
            if self.dataset_type not in self.train_files.keys():
                raise ValueError(f"Invalid training dataset_type. Expected one of {list(self.train_files.keys())}")
            df = pd.DataFrame()
            for file in self.train_files[self.dataset_type]:
                label = "positive" if "pos" in file else "negative" if "neg" in file else None
                with open(file, 'r', encoding='utf-8') as file:
                    tweets = file.readlines()
                tmp_df = pd.DataFrame(tweets, columns=["tweet"])
                tmp_df["label"] = label
                df = pd.concat([df, tmp_df], ignore_index=True)
            return df

    '''
    def load_test_data(self, dataset_type="test"):
        if dataset_type not in test_file.keys():
            raise ValueError(f"Invalid test dataset_type. Expected {list(train_files.keys())}")
        df = pd.DataFrame()
        with open(self.test_file[dataset_type], 'r', encoding='utf-8') as file:
            data = [line.split(',', 1) for line in file.readlines()]
        df = pd.DataFrame(data, columns=["id", "tweet"])
        return df
    '''
    
    def save_df_to_csv(self, df, output_file):
        df.to_csv(output_file, index=False)
        
    def nulls_info(self, df):
        return df.isnull().sum()
    
    #def profile(self, df):
        #profile = ProfileReport(df, title="Twitter Sentiment EDA Report", minimal=True)
        #profile.to_file(self.prj_dir / f"reports/twitter_sentiment_eda_{self.dataset_type}.html")
    
    def process_dataframe(self, df):
        """
        Process the DataFrame based on the specified policies.
        
        Args:
        df (pd.DataFrame): The input DataFrame.
        df2 (pd.DataFrame, optional): The second DataFrame for shared duplicates processing. Default is None.
        
        Returns:
        tuple: The processed DataFrame(s). If df2 is None, returns (df,). Otherwise, returns (df, df2).
        """
        # 1. Handle null values
        if self.preprocessing_policy.get("handle_null"):
            df = df.dropna()
            print('-------------------------------- nulls removal completed')
        
        # 2. Handle duplicates
        if self.preprocessing_policy.get("handle_duplicates"):
            if self.duplicates_policy == "drop":
                df = df.drop_duplicates()
            elif self.duplicates_policy == "keep":
                df = df[df.duplicated(keep=False)]
            print('-------------------------------- duplicates handling completed')
            
        # 3. Handle conflicting tweets
        if self.preprocessing_policy.get("handle_conflicting_tweets"):
            conflict_tweets = df[df.duplicated(subset='tweet', keep=False)]
            if self.conflict_policy == "drop":
                df = df[~df['tweet'].isin(conflict_tweets['tweet'])]
            elif self.conflict_policy == "keep":
                df = conflict_tweets
            print('-------------------------------- conflicting tweets completed')
            
        # 4. Lowercase
        if self.preprocessing_policy.get("lowercasing"):
            df['tweet'] = df['tweet'].apply(lambda x: x.lower())
            print('-------------------------------- lowercasing completed')
        
        # 5. Remove <user> and <url>
        if self.preprocessing_policy.get("tag_removal"):
            df['tweet'] = df['tweet'].str.replace('<user>', '', regex=False)
            df['tweet'] = df['tweet'].str.replace('<url>', '', regex=False)
            print('-------------------------------- tag removal completed')
        
        # 6. Whitespace Stripping
        if self.preprocessing_policy.get("whitespace_stripping"):
            df['tweet'] = df['tweet'].apply(lambda x: x.strip())
            df['tweet'] = df['tweet'].apply(lambda x: " ".join(x.split()))
            print('-------------------------------- whitespace stripping completed')
        
        # 7. Expand contractions
        if self.preprocessing_policy.get("handle_contractions"):
            df['tweet'] = df['tweet'].apply(contractions.fix)
            print('-------------------------------- contractions handling completed')

        # 8.1 De-emojize [Creativity]
        if self.preprocessing_policy.get("de_emojze"):
            df['tweet'] = df['tweet'].apply(lambda x: emoji.demojize(x, delimiters=(" ", " ")))
            df['tweet'] = df['tweet'].replace(":", "").replace("_", " ")
            print('-------------------------------- de-emojization completed')
        
        # 8.2 De-emoticonize [Creativity]
        if self.preprocessing_policy.get("de_emoticonize"):
            pattern = re.compile('|'.join(map(re.escape, emoticon_meanings.keys())))
            df['tweet'] = df['tweet'].apply(lambda tweet: pattern.sub(lambda x: emoticon_meanings[x.group()], tweet))
            print('-------------------------------- de-emoticonization completed')

        '''
            cosa c'è:
            9. togliere hashtags -> rimuovi simbolo e spezza
            10. toglere punteggiatura, simboli, numeri e spazi in eccesso, lettere ripetute
            12. togliere slang (prima di spelling perche riduce il numero di parole mispelled, molto ricco di slang twitter)
            13. rimuovere errori spelling
            12. togliere stop-words'''
        
        # 9. Hashtag removal
        def process_hashtags(tweet):
            '''This function addresses the hashtag removal task.
                Identifies hasthags, removes hashtag's symbol and split content into words'''
            # 9.1 - split tweet
            words = tweet.split()
            # 9.2 - iterate over words
            new_words = []
            for word in words:
                # 9.3 - if word begins with hashtag
                if word.startswith('#'):
                    if self.hashtag_policy == "keep":
                        # 9.4 - split hashtag into list of single words 
                        words = wordninja.split(word.lstrip("#"))
                        # 9.5 - join list of words into single string
                        split_words = " ".join(words).lower()
                        # 9.6 - append to list of words of the tweet
                        new_words.append(split_words)
                    elif self.hashtag_policy == "drop":
                        # Split tweet into words
                        words = tweet.split()
                        # Filter out words that start with a hashtag
                        new_words = [word for word in words if not word.startswith('#')]
                        # Join the words back into a single string
                        new_tweet = ' '.join(new_words)
                    else:
                        raise ValueError("Wrong hashtag_policy provided.")
                else:
                    # 9.7 - if not hashtag simply add words to the list of words of the tweet
                    new_words.append(word)
            # 9.8 - merge all words of the tweet together
            new_tweet = ' '.join(new_words)
            return new_tweet
        if self.preprocessing_policy.get("hastag_handling"):
            df['tweet'] = df['tweet'].apply(lambda x: process_hashtags(x))
            print('-------------------------------- hashtag removal completed')

        # 10. tweet cleaning
        def remove_punctuation_symbols_digits_spaces(tweet):
            ''''This function does a general cleaning of the tweets.
                Operations:
                    - put tweet into lowercase
                    - remove retweet symbol
                    - remove digits and symbols
                    - remove extra blank spaces
                    - remove single letters
                    - reduce repeated letters
                    - replace 'ahahaha' with 'laugh'
                    - replace 'xoxo' with 'kiss'
                    '''
            # 10.1 - remove retweet symbol 'rt' NO BECAUSE THE TEST SET CONTAIN A TWEET WITH ONLY: rt <user> <user>
            #tweet = re.sub(r'\brt\b', '', tweet)
            # 10.2 - keep only letters, numbers, rt and specific symbols
            pattern = r'[^a-zA-Z0-9\(\)rt\?!\s]'
            tweet = re.sub(pattern, '', tweet)
            #tweet = re.sub(r'[^a-zA-Z\s]', '', tweet)
            # 10.3 - remove extra blank spaces
            #tweet = re.sub(r'\s+', ' ', tweet).strip()
            # 10.4 - remove single letter (mostly errors or 'I' which are not useful)
            #tweet = re.sub(r'\b\w\b', '', tweet)
            # 10.5 - reduce repeated letters at the end of the word
            #tweet = re.sub(r'(\w*?)(\w)(?![ls])\2{1,}', r'\1\2', tweet)
            # 10.6 - replace 'ahahahah' and similar with 'laugh'
            #tweet = re.sub(r'\b(?:[ah]*h[ah]*){2,}\b', 'laugh', tweet)
            # 10.7 - replace 'xoxo' and similar with 'kiss'
            #tweet = re.sub(r'\b(xo)+x?\b', 'kiss', tweet)
            return tweet
        if self.preprocessing_policy.get("handle_punctuation"):
            df['tweet'] = df['tweet'].apply(lambda x: remove_punctuation_symbols_digits_spaces(x))
            print('-------------------------------- punctuation removal completed')

        # 11. replace slang
        def replace_slang(tweet, slang_dict):
            '''This function replaces slang words with regular expressions
                For each word in the tweet it checks if it belongs to the slang dictionary and if it does the word gets replaced '''
            # 11.1 - split tweet
            words = tweet.split()
            # 11.2 - iterate over tweet's words
            new_words = []
            for word in words:
                # 11.3 - if words belongs to the slang dictionary
                if word.lower() in slang_dict:
                   # 11.4 - word gets replaced by its regular corresponding
                    new_word = slang_dict[word.lower()]
                else:
                    # 11.5 - else keep word unchanged
                    new_word = word
                # 11.6 - append word to list of words of the tweet
                new_words.append(new_word)
            # 11.7 - merge all words of the tweet together
            new_tweet = ' '.join(new_words)
            return new_tweet
        if self.preprocessing_policy.get("replace_slang"):
            df['tweet'] = df['tweet'].apply(lambda x: replace_slang(x, slang_dict))
            print('-------------------------------- slang replacement completed')

        # 12. correct spelling
        def correct_spelling(tweet):
            '''This function corrects the spelling of the words.
                Using SymSpell algorithm to correct spelling, if no correction is found the original spelling is kept'''
            # 12.1 - get suggestions for the input tweet
            suggestions = sym_spell.lookup_compound(tweet, max_edit_distance=2, transfer_casing=True)
            # 12.2 - if there is a suggestion
            if suggestions:
                # 12.3 - take the closest suggestion
                tweet = suggestions[0].term
            # 12.4 - if there is no suggestion keep the spelling unchanged
            return tweet
        if self.preprocessing_policy.get("correct_spelling"):
            df['tweet'] = df['tweet'].progress_apply(lambda x: correct_spelling(x))
            print('-------------------------------- spelling check completd')

        # 13. remove stopwords
        def remove_stopwords(tweet):
            '''This function removes stopwords from the tweet
                For each word in the tweet it checks if it belongs to the NLTK stopwords set and if it does the word gets replaced '''
            # 13.1 - set of english stopwords
            stop_words = set(stopwords.words('english'))
            # 13.2 - split tweet
            words = tweet.split()
            # 13.3 - iterate over each word of the tweet
            new_words = []
            for word in words:
                # 13.4 - if word is not found in the stopword set
                if word.lower() not in stop_words:
                    # 13.5 - append this word to the tweet words list
                    new_words.append(word)
            # 13.6 - merge all words of the tweet together
            new_tweet = ' '.join(new_words)
            return new_tweet
        if self.preprocessing_policy.get("remove_stopwords"):
            df['tweet'] = df['tweet'].apply(lambda x: remove_stopwords(x))
            print('--------------------------------  stopwords removal completed')

        # 14. lemmatization
        # 14.1 - initialize the WordNet lemmatizer
        lemmatizer = WordNetLemmatizer()
        # 14.2 - assigns part-of-speech tags to each word
        def get_pos(treebank_tag):
            ''' This function converts Treebank POS tags (NLTK) to WordNet POS tags
                - Treebank POS Tags: tags used by the POS tagger in NLTK
                - WordNet POS Tags: tags used by the WordNet lemmatizer'''
            # 14.2.1 - case 1: adjective, map J -> Wordnet.ADJ 
            if treebank_tag.startswith('J'):
                return wordnet.ADJ
            # 14.2.2 - case 2: verb, map V -> Wordnet.VERB
            elif treebank_tag.startswith('V'):
                return wordnet.VERB
            # 14.2.3 - case 3: noun, map N -> Wordnet.NOUN 
            elif treebank_tag.startswith('N'):
                return wordnet.NOUN
            # 14.2.4 - case 4: adverb, map R -> Wordnet.ADV 
            elif treebank_tag.startswith('R'):
                return wordnet.ADV
            # 14.2.5 - case 5: if no match found default is NOUN
            else:
                return wordnet.NOUN
        # 14.3 - lemmatize each word in a tweet based on its POS tag
        def lemmatization(tweet):
            '''This function lemmatizes the words in a tweet based on their POS tags using WordNetLemmatizer'''
            # 14.3.1 - split tweet
            words = tweet.split()
            # 14.3.2 - get POS tags for each word
            pos_tags = pos_tag(words)
            # 14.3.3 - lemmatize each word with its POS tag
            lemmatized_words = [lemmatizer.lemmatize(word, get_pos(tag)) for word, tag in pos_tags]
            # 14.3.4 - merge all lemmatized words of the tweet together
            lemmatized_tweet = ' '.join(lemmatized_words)
            return lemmatized_tweet
        if self.preprocessing_policy.get("lemmatization"):
            df['tweet'] = df['tweet'].apply(lambda x: lemmatization(x))
            print('-------------------------------- lemmatization completed')

        
        '''
        > [Done notebook] Text encoding/ Vectorization
        
        > [Done notebook] Label Encoding
        
    
        Backlog:
            > [backlog] Sarcasm detection [creativity] => change sentiment polarity (heuristic or DL?)
            > [backlog] Dimensionality Reduction [creativity]
            - Si possono mettere parole chiave come alert? Tipo 'guerra'? O è cheating?
            - Padding/Truncation
        '''

        return df
        

