# Mobility Counts Prediction
# 
import streamlit as st
import pandas as pd

# Import custom modules
import module_ai
import module_data
import module_census
import wx


# helper functions / hooks for object calls
def train_model(ai, normalized_df, in_cols, target_col):
    # setup training data
    ai.features = in_cols
    ai.target = target_col
    x_train, y_train, x_test, y_test = ai.format_training_data(normalized_df)

    # init the model
    ai.model_init(x_train)

    # train the model
    ai.train(ai.model, x_train, y_train, x_test, y_test)

    return 

def test_model(ai, normalized_df, in_cols, target_col):
    # setup training / test data
    ai.features = in_cols
    ai.target = target_col
    x_train, y_train, x_test, y_test = ai.format_training_data(normalized_df)

    # load the model or use a model that's already loaded
    if ai.model != None:
        ai.test(ai.model, x_test, y_test)
    else:
        if(ai.model_load(x_test)):
            predictions, y_test, test_loss, test_accuracy = ai.test(ai.model, x_test, y_test)
            return test_accuracy
        else:
            print("No model loaded!")
            return 0

    return test_accuracy

def find_string_index(alist, search_string):
    alist = list(alist)
    try:
        return alist.index(search_string)
    except ValueError:
        return False

# run setup
@st.cache_data
def setup(filePath):
    # init ai module
    ai = module_ai.ai()

    # init data module
    source_data = module_data.data()
    source_data.OUTPUT_FILE_PATH = filePath

    # init census data (using saved data for now)
    # census_dataobj = module_census.census_data()
    # census_data = census_dataobj.get_population_data_by_city(25)

    # setup data sources
    census_df = pd.DataFrame() #pd.DataFrame(census_data)
    result_df = source_data.read()
    normalized_df = source_data.normalized()

    return census_df, result_df, normalized_df, ai, source_data


# GUI home page
st.title("Mobility Traffic Counts AI Prediction")
tab1, tab2 = st.tabs(["1. Train Model","2. Test Model"])

# GUI tab #1: Train Model
with tab1:
	st.header("Train a Traffic Counts Model")
	
	# FilePicker - Choose source data file
	if st.button("Choose source data file"):
		ap = wx.App()
		ap.MainLoop()
		dialog = wx.FileDialog(None,"Select a folder:", style=wx.FD_DEFAULT_STYLE)
		st.session_state.dialog = dialog
		if dialog.ShowModal() == wx.ID_OK:
			folder_path = dialog.GetPath() # folder_path will contain the path of the folder you have selected as string
			census_df, result_df, normalized_df, ai, source_data = setup(folder_path)
		else:
			census_df = pd.DataFrame()
			result_df = pd.DataFrame()
			normalized_df = pd.DataFrame()
			ai = module_ai.ai()
			source_data = pd.DataFrame()
	elif 'dialog' not in st.session_state:
			census_df = pd.DataFrame()
			result_df = pd.DataFrame()
			normalized_df = pd.DataFrame()
			ai = module_ai.ai()
			source_data = pd.DataFrame()
	else:
		folder_path = st.session_state.dialog.GetPath() # folder_path will contain the path of the folder you have selected as string
		census_df, result_df, normalized_df, ai, source_data = setup(folder_path)
	
	# Raw data pane
	st.header("Raw Data")
	st.dataframe(result_df[0:50])

	# Normalized data pane
	st.header("Normalized Training Data")
	st.dataframe(normalized_df[0:50])
	
	# Choose input column(s) drop-down menu
	cols1 = source_data.features_training_set
	in_cols = st.multiselect(label="Choose input column(s) (select one or more):", options=cols1, default=source_data.features_training_set)
	
	# Choose target column
	cols2 = normalized_df.columns
	target_col = st.selectbox(label="Choose target column (select only one):", options=cols2, index=find_string_index(cols2, source_data.features_target))
	
	if st.button('Train Model'):
		st.write('Model training started...')
		result = train_model(ai, normalized_df, in_cols, target_col)
		st.write(result)
	
	
# GUI tab #2: Test/Use Model
with tab2:
	st.header("Test a Traffic Counts Model")
	
	# Input column(s) and target column GUI buttons (previous single window)
	list_of_model_files = ai.get_model_list('..\models')
	ai.model_filename = st.selectbox(label = 'Choose a model file', options=list_of_model_files)
	if st.button('Test Model'):
		st.write('Model testing started...')
		test_accuracy = test_model(ai, normalized_df, in_cols, target_col)
		st.write('Model Accuracy = ', test_accuracy)

# -------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------