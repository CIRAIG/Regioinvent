# Methodology of regioinvent

This document describes in details the methodology that is followed by regioinvent to regionalize ecoinvent to its 
fullest potential.
Note that all the steps to derive the trade data are provided in the forms of Jupyter notebooks in the doc/ folder.

The methodology is divided into multiple sections:
1. [Selection of the trade database](#selection-of-the-trade-database)
2. [Estimation of production data](#estimation-of-production-data)
3. [Correcting for re-exports](#correcting-for-re-exports)
4. [Selection of commodities to regionalize](#selection-of-commodities-to-regionalize)
5. [Selection of countries for regionalization](#selection-of-countries-for-regionalization)
6. [Regionalizing - creating national production process](#regionalizing---creating-national-production-process)
7. [Regionalizing - creating global production market processes](#regionalizing---creating-global-production-market-processes)
8. [Regionalizing - creating national consumption market processes](#regionalizing---creating-national-consumption-market-processes)
9. [Modeling transportation in the created markets](#modeling-transportation-in-the-created-markets)
10. [How to deal with multiple technologies of production](#how-to-deal-with-multiple-technologies-of-production)
11. [Dealing with yearly fluctuation of trade data](#dealing-with-yearly-fluctuation-of-trade-data)
12. [Spatialization of elementary flows](#spatialization-of-elementary-flows)
13. [Regionalized life cycle impact assessment methods](#regionalized-life-cycle-impact-assessment-methods)
14. [Connecting ecoinvent processes to UN COMTRADE commodities](#connecting-ecoinvent-processes-to-un-comtrade-commodities)
15. [Connecting ecoinvent geographies to UN COMTRADE geographies](#connecting-ecoinvent-geographies-to-un-comtrade-geographies)
16. [Connecting EXIOBASE sectors to UN COMTRADE commodities](#connecting-exiobase-sectors-to-un-comtrade-commodities)
17. [Connecting EXIOBASE geographies to UN COMTRADE geographies](#connecting-exiobase-geographies-to-un-comtrade-geographies)
 

### Selection of the trade database
The trade database that is used in regionvent is the UN COMTRADE database (https://comtradeplus.un.org/TradeFlow). The
advantage of this database compared to other candidates (such as Multi-Regional Input-Output tables) is its completeness.
When the most detailed IO databases describe an economy in maximum 500 sectors, the UN COMTRADE database covers the trade
at a much finer level (i.e., thousands of different commodities). In addition, it covers all countries worldwide, while
IO databases tends to aggregate smaller economies.

However, the UN COMTRADE database has inconsistencies. Imports and exports are not reported in the same values (CIF vs FOB).
Furthermore, there are a few missing data points for some years/commodities/countries combinations, as well as blatant
reporting mistakes. In the first versions of regionvent (< v1.2) we tried to correct these inconsistencies ourselves. 
Unfortunately it is very time-consuming and requires a lot of expertise which we lack. Therefore, from the v1.2 of 
regioinvent onward, we rely on the BACI database (https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37), 
which is an adaptation of the UN COMTRADE database where the aforementioned inconsistencies are already corrected.

### Estimation of production data
While the UN COMTRADE provides import and export data with extreme precision, both for commodities and countries, there
is a significant lack of similar data for production. Indeed, to the best of my knowledge, there is no comprehensive 
database with as much detail as the COMTRADE database for national production volumes. Therefore, how can we estimate 
these national production volumes? Because we need this data to have a proper representation of the supply chains.

A first approach, the most logical one, would be to scrap the Internet to "simply" gather this data which most probably
exists but is not centralized in a database. The problem is that we are talking about getting national production data
for thousands of commodities in many countries, so probably more than 200,000 production data to find. Furthermore, some
of these commodities will just not have production volumes available, because the existence of these commodities is more
linked to ecoinvent than to actually existing. Think for instance about "hard chromium coat, electroplating, steel 
substrate, 0.14 mm thickness". Sure there might be specific providers. But good luck to find national production volumes.

This approach is therefore something regioinvent will strive towards slowly, but cannot be the only approach used in 
regioinvent. We need a logical way of estimating national production volumes automatically, based on the data available.

So how to proceed in the meantime? We have thought of two ways to estimate production data, which require minimal to 
basically no additional information.
1. We can estimate national production data based on the export data provided by UN COMTRADE, scaled with the ratio 
production/export which can be obtained from Input-Output databases. **This is the approach that is currently implemented 
in regioinvent, using EXIOBASE.** In other words, if Canada exports 1,000 tonnes of tomatoes (we know that 
from UN COMTRADE) and that (according to EXIOBASE) Canada exports 61.6% of its total production of Vegetables, 
fruit, nuts, then we can estimate the total production of apples in Canada to 1,623 tonnes and the domestic consumption
of apples in Canada to 623 tonnes. This approach is extremely
reliant on the ratios provided by the Input-Output database which can sometimes be really wrong. While a few % error is 
not troubling, there are cases where the ratio is estimated to be 0% of export or 0.00001% of export, which can lead
to significant distortions of the estimation. Furthermore, this approach is subject to typical aggregation bias of
the IO approach, as any "Vegetables, fruit, nuts" will have the same national production/export ratio. And finally, the
calculated ratio is based on financial data and is then reapplied to physical data which further create inconsistency as
the price of commodities is typically not the same between exported products vs domestically consumed products.
2. We can estimate national production data based on the global production data of commodities, redistributed through
their share of the global export. In other words, if we get the global production data (say 100,000 tonnes for apples)
we can then apply the share of each country to the global export market (provided by the UN COMTRADE). So if Canada
represents 3% of the global export of apples, then we consider that Canada also represent 3% of the global production, 
which leads to an estimate of 3,000 tonnes of apples produced in Canada, from which we subtract the export values 
according to UN COMTRADE to derive a domestic consumption estimate. This approach requires finding global production 
data for each of the commodities, which is less daunting but still a big undertaking. However, it straight up 
considers that export and total production are 100% correlated, which is wrong.

Both of these approaches yield poor estimations. We tested these two approaches to estimate national production volumes
of bananas and natural gas (which we got from two reliable sources) and saw that the approach with the export/production
ratios (currently implemented in regioinvent) was about 80% off. The other though (with global production volumes) was 
more like 200% off. The reason why both completely struggle is because there are many cases where countries produce, but
100% consume domestically and thus do not export anything. A perfect example of that would be the production of iron ores
in China. Because China only imports iron ores, with the two approaches, it is undertanding that China does not produce
iron ores, since it's not exporting any. While in reality, we know that, yes, China actually produces iron ores (a lot
actually).

To compensate for mistakes like this, we try to connect to existing production volume databases for a few commodities.
In v1.4, we have connected to FAOSTAT for both agriculture and forestry products, the USGS for mineral extraction and
production of basic metals, to the World Steel Association data for production on basic steel products, to the OICA data
for production on vehicles and finally to the PRODCOM database of the EU for partial production data on many commodities.
For the latter, since it only covers European country and has many data gaps, whenever a data point was provided by this 
data source it was later completed through the approach with EXIOBASE. So it's a hybrid approach that can (and maybe will)
be applied in the future to other partial production data.

Note that relying on production/export ratios from EXIOBASE creates huge inconsistencies for cases when the ratio is 
estimated to be extremely close to 100% or 0% (e.g., 99.99998%), which can happen due to artefacts. To solve this, we
fixed the upper and lower bounds of these ratios to 99.9% and 0.1%. Meaning that if a ratio was between 99.9% and 100%,
they were forcibly set to 100% (and respectively between 0.1% and 0%).


### Correcting for re-exports
Within the UN COMTRADE database (and it's the same in the BACI database) there is limited to no difference between exports
and re-exports. What is a re-export? Think about the Netherlands. You are a country with a powerful naval trading history
and fleet. What you typically do is import commodities and resell them in Europe directly. For example, the Netherlands
are the 7th biggest exporters of bananas in the world. Now in case you are not shocked by this, the issue is that bananas
do not grow in the Netherlands. And our algorithm uses exports to estimate production volumes. If nothing is done, the 
Netherlands will be identified as a big producer of bananas. That is why re-exports must be corrected somehow.

Our contingency plan ended up being to simply use net exports instead of exports. Net exports are the difference of 
exports and imports. So if a country, such as the Netherlands, does a lot of re-exports, they will definitely import 
more than they export, and thus have a net export of zero, or a negative one. Big producers will most likely have a 
positive net export balance (although we come back to the iron ores in China example), while smaller producers might 
still have a negative net export balance and will thus not be identified as producers. This is the best contingency plan
we could think of though.

Since now re-exports were excluded, we need to readjust the imports as well, because some of them were importing through
re-exports. For instance, maybe Poland was buying bananas from the Netherlands. So to do that, we just go through the 
import list and check if there is an estimated national production for the commodity/country combination of the import
and if not (think again banana/NL), we take the value of the import and re-assign it to the 5 biggest exporters of the
commodity. So if Poland was buying 10,000,000$ of bananas from the Netherlands, these 10,000,000$ will be split between
the 5 biggest exporters of bananas, e.g., Ecuador, etc.

### Selection of commodities to regionalize
In regioinvent v1.3, there was a switch in philosophy. In previous versions, the focus was put on internationally-traded
commodities, simply because they were the reason behind the introduction of consumption markets. However, it left a lot
of processes non-regionalized, which did not make much sense sometimes. The production of HFC-152a was regionalized, but
the hot-rolling of steel was not, and regioinvent was thus still relying on RoW or GLO processes for transformation (for
example). So in v1.3, we now regionalize  non-internationally traded commodities as well. However, regionalizing
them all would explode the size of the resulting database. We therefore onlt regionalized the most relevant of them.

How do we determine which non-internationally traded commodities are relevant or not? For example, is "tap water" more
relevant than "waste cement, hydrated"? To decide, we look at the contributions of these commodities among all the 
processes of ecoinvent. You can follow the steps we describe below on the "Choosing which process to regionalize.ipynb"
jupyter notebook. Then, if "tap water" contributes more to impact categories than "waste cement, hydrated", then tap water
will be considered relevant (and thus will be regionalized) while waste cement, hydrated will be considered irrelevant
(and thus won't be regionalized).

We do the contribution analyses on all processes of ecoinvent, except market processes as the contribution of any commodity
within their market will simply be 100%. That's around 13,000 and so around 13,000 contribution analyses to run. Then, 
we need to decide how to weight the contributions on different impact categories. Maybe tap water is relevant for climate
change, but that waste cement, hydrated is relevant for ionizing radiations. We rely on IW+ and the scientific weighting
that is used to go from damage categories to the two area of protection (in DALY and in PDF.m2.yr). In the 13,000 contribution
analyses we then only take the commodities which contribute on average (that is, across the 13,000 processes) to at least
0.3%. 0.3% sounds random as a number and it kind of is. 1% would lead to barely nothing being regionalized for 
non-internationally traded commodities, while 0.1% would lead to too many processes to regionalize. 0.3% leads to a
manageable amount of extra regionalization to do (~75 commodities depending on the ei version). These commodities are 
listed in the relevant_non_traded_products.json files which is then used by the code. If a user wants the maximum 
possible regionalization they can input the whole list of commodities of ecoinvent in this json file. But be warned.
You will most likely require a super computer to run that. Or at the very least a good 32GB of RAM with a good 
CPU/SSD drive for it not to take forever to run.

### Selection of countries for regionalization
Ideally, the commodities could be regionalized for all countries in the world. Practically speaking though, there
is clearly a constraint of calculation power. The more processes are created, the longer and harder the calculations will
be. Therefore, regioinvent only regionalizes for countries that are deemed relevant for each commodity. Why would I create
a banana production process in Canada while Canada probably does not even produce bananas. How do we choose which countries
are relevant? We look at the production and consumption data and cut-off any country lower than X% of the cumulative sum,
X being the cutoff selected by the user. By default this cutoff is set to 99%.
So concretely, if we have such a distribution for production: China 75%, US 20%, Canada 4.5%, Peru 0.4%, Chile 0.1%, we 
calculate the sorted cumulative sum of the production: 
1. China 75%
2. China + US 95%
3. China + US + Canada 99.5%
4. China + US + Canada + Peru 99.9% 
5. China + US + Canada + Peru + Chile 100%

As soon as the cumulative sum passes the cutoff threshold, any country remaining will be aggregated in a Rest-of-the-World 
(RoW) region. 

So in the little example provided, if working with a 99% cutoff, processes for China, the US and Canada 
would be created, but processes for Peru and Chile would not be created. Instead, a RoW process would be created based 
on the production data of all aggregated countries (Peru and Chile in this example).

If the cutoff was 90% instead, only process for China and the US would be created and Canada, Peru and Chile would be 
aggregated as RoW.

The higher the cutoff, the more countries are covered in the regionalization of each product, the more processes there are.

The same principal is applied with consumption data. Production data is used for determining the producing countries 
that will be represented, while consumption data is used to determine for which countries consumption markets will be
created.

So this is for internationally-traded commodities where we can base our geographies-to-cover on trade. What about 
non-internationally-traded commodities (and transformation activities). For them, we first thought of regionalizing
for the geographies that were required given the cutoff selected. If no process in the database is gonna use "chemical
factory, organics" in Andorra, why create it? The problem is that determine this list of used commodities/geography
combination is actually extremely tricky to get, because everytime you add more geographies, these new geographies 
require new commodities/geography combination to be created as well. And it basically snowballs. So instead of doing that
we just directly regionalize for all the geographies used within regioinvent (which can be found in the 
geographies_of_regioinvent.json files).

The effect of the cutoff selection on the results was estimated between the cutoff: 99%, 90% and 75%. You can see these
effects applied to the IW+ v2.1 LCIA method in the regioinvent article. Overall, if we
consider that the 99% cutoff provides the most accurate results, going from 99% to 90% triggers differences of about
~1 to 2% on most of the impact categories, but reduces the size of regionvent from ~230,000 processes to ~85,000. 
Going from 99% to 75% leads to differences of ~2 to 3%, but reduces the size to ~42,000 processes. Essentially, if you
cannot work with the 99% cutoff, because it takes too long or you don't have enough RAM, working at lower cutoffs is not
that impacting overall. Do note that on certain impact categories, i.e., freshwater acidification, freshwater 
ecotoxocity, short term and water availability human health, the differences are between 6% and 50%. You can access the
full comparison in the Excel file "Effect of cutoff" in the doc/ folder.

### Regionalizing - creating national production process
Each combination of commodity/country previously selected is created within regioinvent. How do we go about that? Well
we simply automate what LCA practitioners worldwide already do manually. We simply copy the most relevant existing process
within the ecoinvent database and sprinkle some regionalization on it, namely, we regionalize the electricity, heat and 
municipal solid waste (MSW) treatment processes, and we also spatialize the elementary flows. <br>
__*In the end, regioinvent only adapts the origin of flows and does not modify values.*__ <br>

Technically speaking, we identify all existing geographies for each of the adapted inputs and store these in json files:
(for example see Data/Regionalization/ei3.x/electricity_processes.json). That way the code knows that it can look for
existing processes within the ecoinvent database and switch them within the national production process created. It's 
kind of ugly and you could tell me that we could have just looked "in real-time" instead by searching through the 
brightway2 database, but turns out this is waaaay longer.<br>

To know which region is best adapted to each country, we stored this information in another json file (see 
Data/Regionalization/ei3.x/country_to_ecoinvent_regions.json). Concretely, the problem is that if the previous selection
steps require to create a process for the production of *random_commodity1* in France, we must identify what is the 
closest available process in ecoinvent. And so the code will go into the json file, and see that France is linked to the 
following potential ecoinvent regions ["RER", "IAI Area, EU27 & EFTA", "RER w/o DE+NL+RU", "RER w/o CH+DE", 
"Europe without Switzerland and Austria", "Europe without Switzerland", "Europe without Austria", "RER w/o RU", 
"RoE", "UCTE", "UCTE without Germany", "WEU"]. If none of these regions are defined, then the code will search for a RoW
or GLO process instead. And if not even GLO and RoW process exist (which is the case for "aluminium, primary, ingot" or
for "land tenure, arable land, measured as carbon net primary productivity, annual crop" for 
example), then the code will select a random available geography to be the base for the copy.

### Regionalizing - creating global production market processes
The export data from the BACI database is combined with domestic production estimates to form a total production
data. Then it is simply extracted for each commodity and used. Transportation is also added (see 
[Transportation section](#modeling-transportation-in-the-created-markets)).

### Regionalizing - creating national consumption market processes
The import data from the BACI as well as the estimated domestic consumption data are summed up together to obtain
consumption data per country. Then this data is simply used to generate consumption markets. Transportation is also 
added (see [Transportation section](#modeling-transportation-in-the-created-markets)).

### Modeling transportation in the created markets
In the global production market and various national consumption markets created by regioinvent, transportation modes must be
added. Regioinvent v1.3 only simply copies the transportation distribution of the ecoinvent markets providing the commodity, 
adds it to the new market for regioinvent (either consumption market or production market), and averages it. 
This simple copy and paste creates inconsistencies by adding transportation modes that are
unadapted to the actual transportation that would occur between two countries. For example, there are processes of 
transportation by tanker for imports from Germany to Switzerland, which obviously makes no sense. In later version of 
regioinvent, we intend to regionalize at the very least the transportation distances and modes depending on the origin
and destination of each markets within regioinvent. After that, we might even further regionalize transportation by
creating (and thus adapting) transportation modes per countries, so that the tanker that leaves from Shanghai, using
kerosene that is typically bought in China, instead of using the GLO or RoW kerosene markets. But once again there is a 
compromise to-be-made between adding more regionalization and calculation time when performing LCAs.

### How to deal with multiple technologies of production
Some commodities can be produced through various means. For instance, 1-butanol can be produced through the 
"hydroformylation of propylene" but also through "synthetic fuel production, from coal, high temperature Fisher-Tropsch 
operation". Production and trade data however, are only provided for the commodity overall. How then can we distribute
each national market shares to the different technologies? Well in regioinvent, we calculate the distribution of the 
technologies within the global production market of ecoinvent (or its closest substitute if there is no GLO market, e.g, RoW) and
then simply reapply that technology share, to the national share. So, more concretely, if the hydroformylation of 
propylene represents 80% of the production of 1-butanol overall, and that Canada represents 10% of global production 
shares for 1-butanol, then regioinvent creates a Canadian process for both hydroformylation and Fisher-Tropsch, and adds
their respective shares (10% * 80% = 8% and 10% * 20% = 2%) for both technologies. <br>
What does this choice entails? This assumption does not respect the actual technologies implemented nationally. 
Fisher-Tropsch from coal is probably not a technology that is used in Europe to produce 1-butanol for example, but is used
in South Africa. But with the assumption made, we consider that Europe and South Africa produce 1-butanol with both 
technologies. Refining these choices entails a deep expertise of technologies deployed throughout the world, and for many
different commodities. However, this is not an expertise that is available to regioinvent's team.

For non-internationally traded commodities, the shares of the ecoinvent markets are also simply copied and re-applied. 
The difference with the consumption and production markets, is that we need to create another "market" for the distribution
of these technologies producing non-internationally traded commodities (think of tap water, which can be produced from 
"conventional treatment" or "direct filtration treatment"). Because just copying the ecoinvent markets and keeping their
names would be confusing (you would have consumption markets, production markets and just "markets" and it's not clear
what they are) we rename them. What markets are in ecoinvent are actually technology mixes. So we decided to create
"technology mix for xxxx" processes to represent these distributions. So when you see a process "technology mix for" 
think of the markets of ecoinvent.

### Dealing with yearly fluctuation of trade data
To not be subject to the whims of the trade market changing constantly, which would affect the robustness from year to 
year of the assessments carried out with regioinvent (and also requiring to redo regioinvent every year), we chose to
take the average trade data over the 5 last years available. For regioinvent v1.4, this mainly corresponds to data for 
the years 2020, 2021, 2022, 2023 and 2024. A simply arithmetic average is performed. <br>
There are a few exceptions for which only the years 2022, 2023 and 2024 were considered because the corresponding commodity only exists 
in the HS22 version of UN COMTRADE, and not in the HS17 version. For instance, the commodity 290341 - trifluomethane (HFC-23)
is only available in HS22, otherwise it would be under 290339 - Other fluorinated, brominated or iodinated derivatives of 
acyclic hydrocarbons, which is much less precise.

Here are the commodities which are only under the years 2022, 2023 and 2024: ['290341', '290343', '290349', '854142', '854143', '854159',
'441881', '441882', '441883']

### Spatialization of elementary flows
The spatialization of elementary flows is an important aspect of the work of regioinvent. However, it is quite easy to 
implement and understand actually. Regioinvent simply allocates the location of the process to the extraction or emission
of relevant elementary flows. What are the relevant elementary flows you ask? Well to determine those, we focused on the
coverage of regionalized impact categories for three LCIA methods: IMPACT World+, ReCiPe and EF. For these three methods,
we simply looked at the different elementary flows for which there are regionalized characterization factors. These are
the relevant elementary flows mentioned previously. Typically, these are: water flows, land flows, acidification flows,
eutrophication flows, photochemical oxidant formation flows and particulate matter flows.

Regioinvent creates a __*biosphere3_spatialized_flows*__ database in your brightway project which contains all these 
relevant spatialized elementary flows, which needed to be created.

Later on, the code simply picks up from this biosphere3_spatialized_flows database to switch non-spatialized elementary 
flows for spatialized elementary flows.

### Regionalized life cycle impact assessment methods
With spatialized elementary flows, characterization factors must be attributed to them, otherwise nothing will be 
characterized and the results will mean nothing. You therefore cannot use regioinvent with the typical packaged methods
of brightway2. To be clear, there won't be any error and everything will work, but for impact categories with spatialized
elementary flows, the results will be wrong.

Regioinvent v1.4 operates with IMPACT World+ v2.2.1,  ReCiPe 2016 v1.03 (H) and EF 3.1. Users are welcome to contribute by 
matching with other impact methods.

### Connecting ecoinvent processes to UN COMTRADE commodities
This step is basically a giant mapping effort to be done between the names of ecoinvent commodities selected for 
regionalization (e.g., "1-propanol") and UN COMTRADE commodity codes (e.g., 290512: "Alcohols; saturated monohydric, 
propan-1-ol (propyl alcohol) and propan-2-ol (isopropyl alcohol)"). This mapping was first based on the existing mapping
provided in the ecospold files as of the 3.10 of ecoinvent. However, the mapping of ecoinvent is lacking in many aspects.
It was thus entirely redone "manually" with the help of ChatGPT-4o. While previous versions of chatGPT struggled with
mapping correctly, chatGPT-4o was capable of doing it reliably. Each mapping was checked again by the programmer.

This mapping can be found in the Data/Regionalization/ei3.x/ecoinvent_to_HS.json files.

### Connecting ecoinvent geographies to UN COMTRADE geographies
Ecoinvent relies on the ISO 2-letter country code while the UN COMTRADE relies on the ISO 3-letter country code system.
Furthermore, COMTRADE has a better resolution in terms of countries than ecoinvent, so there are cases when there is not
a match between the countries in both databases. A mapping is therefore required. 

This mapping can be consulted here: Data/Regionalization/ei3.x/COMTRADE_to_ecoinvent_geographies.json

### Connecting EXIOBASE sectors to UN COMTRADE commodities
Another mapping step. Similarly to the one with ecoinvent, the mapping was conducted manually with the help of chatGPT-4o.
EXIOBASE is mainly based on the CPAv2.1 classification and is used in the domestic consumption estimation approach with 
the national production/export ratios.

This mapping can be found in the Data/Regionalization/ei3.x/HS_to_exiobase_name.json files.

### Connecting EXIOBASE geographies to UN COMTRADE geographies
EXIOBASE relies on the ISO 2-letter country code while the UN COMTRADE relies on the ISO 3-letter country code system.
Furthermore, COMTRADE has a much better resolution in terms of countries than EXIOBASE, so there are cases when there 
is not a match between the countries in both databases. A mapping is therefore required. 

This mapping can be consulted here: Data/Regionalization/ei3.x/COMTRADE_to_exiobase_geographies.json

