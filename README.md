## _Regioinvent_

```Regioinvent``` is a Python package for automatically connecting the _ecoinvent_ database to _BACI_, a trade database.

Connecting to a trade database enables a more realistic description of average supply chains within the ecoinvent database
through the introduction of consumption markets, based on international import data and production data. The result is a
version of ecoinvent which almost does not rely on non-national processes such as RER, RoW or GLO.

Furthermore, since the resulting regionalized version of ecoinvent relies much less on broad regions, the regionalization
of impacts can show its full potential. Therefore, ```Regioinvent``` also fully spatializes all relevant elementary flows
and connects these spatialized elementary flows to regionalized life cycle impact assessment methods. There are currently
three LCIA regionalized methods implemented: IMPACT World+ v2.1 / EF 3.1 / ReCiPe 2016 v1.03 (H).

## Showcase
To showcase what ```Regioinvent``` does, let's illustrate on a random example: the production of diethanolamine in Sweden.

Within ecoinvent, the production of diethanolamine is only available for Europe (RER) and Rest-of-the-World (RoW).

Screenshot below shows the diethanolamine production process for Europe (values are hidden for ecoinvent licensing reason).
Notice how there is absolutely nothing adapted for the Swedish context, which is normal since it's for Europe as a whole.

<img src="images/diethanolamine_rer_production.png" width="600"/>


After running ```Regioinvent``` three types of processes are created.
1. National production processes <br>

National production processes for many countries and all traded commodities of ecoinvent are created automatically.
Below you can see the example for the Swedish production. Now you can see that basically everything is adapted to the 
Swedish context, energy vectors (electricity/heat), consumables (ammonia) and even capital goods (chemical factory).

<img src="images/diethanolamine_swedish_prod.png" width="600"/>

2. National consumption markets <br>

National consumption markets representing the average origin of a commodity purchased in a given country, based on
import and domestic production data are created. Below you can see the example for the Swedish consumption market of 
ammonia that is used in the production of diethanolamine.
We can see that Sweden is importing ammonia mainly from Russia (~73%), from the Netherlands (~7%) and from Algeria (~5%).
Of course, all these national production processes of ammonia were created along all the other national production processes.

<img src="images/ammonia_swedish_consumption_market.png" width="600"/>

3. A global production market <br>

Global production markets, representing the global production shares for each commodity, are also created. Below you can
see the one for the production of diethanolamine which, according to our data, is mostly produced in Saudi Arabia (~55%),
Malaysia (~10%), Belgium (~10%), Germany (~8%) and Sweden (~5%).


<img src="images/diethanolamine_global_production_market.png" width="600"/>


## ```Regioinvent``` in your LCAs
Use the three types of processes generated with ```Regioinvent``` as follows:
- If you know where the production of your commodity occurs, select the corresponding national production process. Either
for the location exactly, or, if unavailable, the RoW version which is an aggregate of all the countries not being in the
biggest producers. (Of course add some transportation on top of these processes to model their distribution)
- If you don't know where the production of your commodity occurs, BUT you know where it was bought, rely on the consumption
markets. These describe where the commodity should come from, on average, given the trade of the region.
- If you don't know anything about the process, you can either use the RoW or GLO process of ecoinvent, or rely on the 
global production process of ```Regioinvent```.

## Get started

Regioinvent can be installed through `pip`.

Install with Brightway2-compatible libraries:

```bash
pip install "regioinvent[bw2]"
```

Install with newer Brightway 2.5-compatible libraries:

```bash
pip install "regioinvent[bw25]"
```

For local development (editable install) from a cloned repository:

```bash
pip install -e ".[bw2]"
# or
pip install -e ".[bw25]"
```

If Brightway libraries are already installed and should not be touched:

```bash
pip install -e . --no-deps
```

You will need a few things to get started:
- Regioinvent does not provide the ecoinvent database, so you need to buy an ecoinvent license yourself.
- Download all the required trade data that were already extracted.
You can download it from [here](https://doi.org/10.5281/zenodo.11583814). Make sure to take the latest available version.
- Install Brightway libraries and have a Brightway project with either ecoinvent3.9.1 cut-off or ecoinvent3.10.1 cut-off.

Note that regioinvent currently only supports the ecoinvent 3.9/3.9.1/3.10/3.10.1 cut-off versions.

You can then follow the steps presented in the [demo.ipynb](https://github.com/CIRAIG/Regioinvent/tree/master/doc/demo.ipynb) 
Jupyter notebook.

Recommended python version: 3.11.8

## How to use after running the code?
Once the regionalized version of ecoinvent is created on Python, it can be exported to your Brightway
project. You will then be able to perform your LCAs either through Brightway or activity-browser as you would with the regular ecoinvent database. <br>
Do note that calculations can be longer with ```Regioinvent``` depending on the cutoff you select. WIth a cutoff of 0.75,
calculations times are similar to ones with normal ecoinvent (a few seconds). With a cutoff of 0.99, the size of the
regioinvent database increases 
dramatically, and so does the calculation time (from 5 to 15 minutes depending on your machine). <br>
There are currently no support for other LCA software, as SimaPro and openLCA are not able to support the size of the
regioinvent database.

## Overview of the methodology

For a deep dive in the methodology of regioinvent, take a look at the Methodology.md file.

<img src="images/brief_methodo.png" width="600"/>

1. Closest available process in ecoinvent is copied and adapted for electricity, heat and waste inputs
2. National consumption markets are created based on import and production data
3. The national consumption markets are connected to the rest of the database
4. Elementary flows are spatialized

## Adaptations
- ```Regiopremise``` (https://github.com/matthieu-str/Regiopremise) is an adaptation of regioinvent that can work with the 
```premise``` library (https://github.com/polca/premise).

## Future developments
Next steps for regioinvent are to:
- operate with the ecoinvent 3.11 version
- adapt the transportation within the different markets to reflect the origins of commodities
- link with the LC-impact LCIA methodology
- derive and integrate uncertainty factors for consumption markets, based on the year-to-year trade variations
- find and integrate more and more real production volumes instead of relying on rough estimates

## Support
Contact [maxime.agez@polymtl.ca](mailto:maxime.agez@polymtl.ca)

## Citation
Citing the code: https://doi.org/10.5281/zenodo.11836125 <br>
Citing the article: https://doi.org/10.21203/rs.3.rs-8159063/v1 <br>
Citing BACI: Gaulier, G. and Zignago, S. (2010) BACI: International Trade Database at the Product-Level. The 1994-2007 Version. CEPII Working Paper, N°2010-23.
