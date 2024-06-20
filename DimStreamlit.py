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

# connect to dimcli
dimcli.login()
dsl = dimcli.Dsl()

# this function connects do dimcli to access the API and queries the publications
# set variable cache_var to the same thing if you want Streamlit to cache the data, change the value 
# if you want to query the data again
@st.cache_data
def load_dimensions_data(cache_var):
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
#other_num = count_publisher[count_publisher['count'] < 10]['publisher'].sum()
count_publisher = count_publisher[count_publisher['count'] >= 10] # delete publishers with <4 publications

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
collabs = pd.DataFrame(columns=['lat', 'long', 'collabNum', 'type', 'countryCode', 'country'])
for orgs_list in pubs['research_orgs']:
    for org in orgs_list:
        if 'latitude' not in org or 'longitude' not in org: # if org doesn't have lat/long info, skip it
            continue
        if org['name'] in GRID_NAMES: # if org is UCSD related, skip
            continue
        if org['name'] not in collabs.index:
            collabs.loc[org['name']] = [org['latitude'], org['longitude'], 1, org['types'][0], org['country_code'], org['country_name']]
        else: # uni already in the dataframe
            collabs.at[org['name'], 'collabNum'] += 1

collabs_country = collabs.groupby(['countryCode', 'country'], as_index=False).sum()
collabs_country = collabs_country.drop(index = 120) # drop US so it doesn't overshadow everything else


# function for creating topic graphs
@st.cache_data
def load_topic_analysis_data(domain):
    print(domain)
    query = f"""
    search publications
        where research_orgs.id = "{GRIDID_LIST[0]}"
        and category_for.name= "{domain}"
        and year=2024
        return publications[id+doi+concepts_scores+year]
    """
    data = dsl.query_iterative(query)  
    concepts = data.as_dataframe_concepts() # turn concepts into df with one row per concept
    concepts_unique = concepts.drop_duplicates("concept")[['concept', 'frequency', 'score_avg']] # process duplicates
    return concepts_unique

def filter_concepts(concepts_unique, freq_min=10, freq_max=70, score_min=0.5, max_concepts=200):
    # Score: the average relevancy score of concepts, for the dataset we extracted above. good indicator of interesting concepts
    # max-concepts to include in the visualization is default 200
    print('Filtering...')
    if freq_max == 100:
      freq_max = 100000000
    
    filtered_concepts = concepts_unique.query(f"""frequency >= {freq_min} & frequency <= {freq_max} & score_avg >= {score_min} """)\
                        .sort_values(["score_avg", "frequency"], ascending=False)[:max_concepts]
    return filtered_concepts


# STREAMLIT DASHBOARD


# UCSD header
st.image(image="ucsd.png")                                                  
bar_chart = px.bar(count_publisher, x='count', y='publisher', title='UCSD Publications by Publisher, 2024',
                   labels={'publisher' : 'Number of publications', 'count' : 'Publishers'},
                   category_orders={'count' : count_publisher['count']})

# selectbox to pick domain for publishers bar chart
# include: Indigenous Studies  ? no publications yet for that category
option = st.selectbox(
    "Choose a domain to view who are the main publishers in that domain:",
    domains,
    index=None,
    placeholder='Select domain...')

# conditional statement to create publisher bar chart based on if a domain has been selected
if option == None:
    bar_chart = px.bar(count_publisher, x='count', y='publisher', title='Top UCSD Publications by Publisher, 2024',
                   labels={'count' : 'Number of publications', 'publisher' : 'Publishers'})
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
map = px.scatter_geo(collabs, lat='lat', lon='long', hover_name=collabs.index, size='collabNum', 
                     color='collabNum', color_continuous_scale="sunset_r", title='Collaborations by University')
map.update_geos(
    visible=False, resolution=50,
    showcountries=True
)
st.plotly_chart(map, use_container_width=True)

map_country = px.choropleth(collabs_country, locations="country", locationmode='country names',
                    color="collabNum",
                    color_continuous_scale=px.colors.sequential.Plasma, title='Collaborations by Country')
st.plotly_chart(map_country, use_container_width=True)

# concept map
option_concept = st.selectbox(
    "Choose a domain to view concepts discussed in recent publications",
    domains,
    index=None,
    placeholder='Select domain...')

def printConcept(min_freq=10):
    if option_concept != None:
        concept_df = load_topic_analysis_data(option_concept)
        filtered_concept_df = filter_concepts(concept_df, min_freq)
        concept_graph = px.scatter(filtered_concept_df,
                                   x="concept",
                                   y="frequency",
                                   height=700,
                                   color="score_avg",
                                   color_continuous_scale=px.colors.sequential.Plasma,
                                   size="score_avg")
        st.plotly_chart(concept_graph, use_container_width=True)
    else:
        filtered_concept_df=None

    return filtered_concept_df

fil_concept_df = printConcept()