# imports
import dimcli
import streamlit as st
import numpy as np
import pandas as pd
import json
import time
import plotly.express as px
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import seaborn as sns



# some variables
GRIDID_LIST = ["grid.266100.3", "grid.420234.3", "grid.413086.8"]
GRID_NAMES = ['University of California, San Diego', 'UC San Diego Health System', 'University of California San Diego Medical Center'] 
FIELDS = "title+type+year+journal+authors+research_orgs+research_org_names+publisher+times_cited+funders+authors_count+category_for"
domains = ('None', '30 Agricultural, Veterinary and Food Sciences', '31 Biological Sciences', '32 Biomedical and Clinical Sciences', '33 Built Environment and Design', 
           '34 Chemical Sciences', '35 Commerce, Management, Tourism and Services', '36 Creative Arts and Writing', '37 Earth Sciences', '38 Economics', '39 Education',
           '40 Engineering', '41 Environmental Sciences', '42 Health Sciences', '43 History, Heritage and Archaeology', '44 Human Society', '46 Information and Computing Sciences',
           '47 Language, Communication and Culture', '48 Law and Legal Studies', '49 Mathematical Sciences', '50 Philosophy and Religious Studies', '51 Physical Sciences', '52 Psychology')


# this function connects do dimcli to access the API and queries the publications
# set variable cache_var to the same thing if you want Streamlit to cache the data, change the value 
# if you want to query the data again
@st.cache_data
def load_dimensions_data(cache_var):
    # connect to dimcli
    dimcli.login()
    dsl = dimcli.Dsl()
    query = f"""search publications
        where research_orgs.id in {json.dumps(GRIDID_LIST)} and year=2024
        return publications[{FIELDS}] sort by year"""
    #result = dsl.query(query)
    result = dsl.query_iterative(query, limit=400)
    return result.as_dataframe()


# get and process data
pubs = load_dimensions_data(cache_var=True)
pubs['funder_name'] = pubs['funders'].apply(lambda x : [] if isinstance(x, float) else [dict['name'] for dict in x])
pubs['overall_cat'] = pubs['category_for'].apply(lambda x : [] if isinstance(x, float) 
                                                                else [dict['name'] for dict in x if not dict['name'][0:4].isdigit()])

# publishers dataframe
count_publisher = pubs['publisher'].value_counts().reset_index()
other_num = count_publisher[count_publisher['publisher'] < 10]['publisher'].sum()
count_publisher = count_publisher[count_publisher['publisher'] >= 10] # delete publishers with <4 publications

# function to filter count_publisher by domain
def createDomainDf(category):
    count_publisher = pd.DataFrame(columns=['publisher', 'count'])
    count_publisher = count_publisher.set_index('publisher')
    
    # loop through all publications and look at their list of categories
    for i in range(0, len(pubs)): 
        curr_cat = pubs['overall_cat'][i] # list of categories
        if category in curr_cat:
            if pubs['publisher'][i] in count_publisher.index.unique():
                count_publisher.loc[pubs['publisher'][i]] += 1
            else:
                count_publisher.loc[pubs['publisher'][i]] = 1

    return count_publisher.sort_values(by=['count'], ascending=False)


# function to create downloadable pdf of domain graphs for publishers
@st.cache_data
def create_pdf_domain_graphs():
    # IMPORTANT: Cache the conversion to prevent computation on every rerun
    figs = []
    pdf = PdfPages('publishers_domain_graph.pdf') # output pdf

    print('Creating figures in a downloadable PDF..')
    for category in domains:
        if category == 'None':
            continue
        print(category)
        sns.set(font_scale=1)
        plt.figure(figsize=(8.5, 11))
        df = createDomainDf(category)
        sns.barplot(x=createDomainDf(category)['count'][0:10], y=createDomainDf(category).index[0:10])
        plt.title('Top 10 Publishers for UCSD Publications in 2024, ' + category[3:] + ' Domain')
        pdf.savefig(bbox_inches='tight')  # saves the current figure into a pdf page
        plt.close()
    
    pdf.close()


# affiliations dataframe
print('Creating dataframe for university collaborations...')
collabs = pd.DataFrame(columns=['lat', 'long', 'collabNum', 'type'])
for orgs_list in pubs['research_orgs']:
    for org in orgs_list:
        if 'latitude' not in org or 'longitude' not in org: # if org doesn't have lat/long info, skip it
            continue
        if org['name'] in GRID_NAMES: # if org is UCSD related, skip
            continue
        if org['name'] not in collabs.index:
            collabs.loc[org['name']] = [org['latitude'], org['longitude'], 1, org['types'][0]]
        else: # uni already in the dataframe
            collabs.at[org['name'], 'collabNum'] += 1




# STREAMLIT DASHBOARD


# UCSD header
st.image(image="ucsd.png")                                                  
bar_chart = px.bar(count_publisher, x='publisher', y='index', title='UCSD Publications by Publisher, 2024',
                   labels={'publisher' : 'Number of publications', 'index' : 'Publishers'},
                   category_orders={'index' : count_publisher['index']})

# selectbox to pick domain for publishers bar chart
# include: Indigenous Studies  ? no publications yet for that category
option = st.selectbox(
    "Choose a domain to view who are the main publishers in that domain:",
    domains,
    index=None,
    placeholder='Select domain...')

# conditional statement to create publisher bar chart based on if a domain has been selected
if option == None:
    bar_chart = px.bar(count_publisher, x='publisher', y='index', title='UCSD Publications by Publisher, 2024',
                   labels={'publisher' : 'Number of publications', 'index' : 'Publishers'})
else:
    bar_chart = px.bar(x=createDomainDf(option)['count'][0:10], y=createDomainDf(option).index[0:10],
                       title='Top 10 Publishers for UCSD Publications in 2024, ' + option[3:], 
                       labels={'x' : 'Number of publications', 'y' : 'Publishers'})

bar_chart.update_layout(yaxis = {'categoryorder' : 'total ascending'})
st.plotly_chart(bar_chart, use_container_width=True)

#download button for pdf of domain graphs, all domains
create_pdf_domain_graphs()

with open("publishers_domain_graph.pdf", "rb") as file:
    st.download_button(
    label="Download domain graphs as PDF",
    data=file,
    file_name="publishers_domain_graphs.pdf"
)

# collab map
st.map(data=collabs, latitude='lat', longitude='long', size='collabNum')    # map of collabs
