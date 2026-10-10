# V2 synthetic Indian-home data and label rules

All bundled household energy labels and behavioral distributions are synthetic. No real annual bills are fabricated.
Weather/solar caches contain separately sourced physical inputs. Sources and parameters live in physics.py and the source-evidence report;
using measured weather does not make the simulated household labels measured or validate this end-use simulator.

## Correlated sampling

Default12,000rows,seed42,four-household building/archetype groups. City probabilities in schema order:
Hyderabad48%,Delhi10%,Mumbai8%,Bengaluru8%,Chennai8%,Kolkata6%,Jaipur5%,Pune7%. These are demo weights,not population estimates.
Group-shared city/type/area/insulation/glazing create dependency; group IDs remain together in all partitions.
Type independent/row/apartment probabilities.32/.18/.50; median areas115/90/80m²,log-sigma.29,bounds35–250m².
Within-group area normal variation4.5%;occupants=clipped(Poisson(2.1+area/140)+1,1,8).
Insulation poor/average/good probabilities.38/.42/.20;single-glazing probability.84ifpoor,.65otherwise.
Fans-only probability.50inBengaluru/Pune,.26elsewhere;remaining standard64%/efficient36%. AC units correlatearea/55,bounded1–5.
Fans-only ACunits/hourszero. ACdailyhours=clipped(gamma(2.4,2.2),.5,16). Capacitymean1.5ton above80m²,1.1otherwise;
ISEERmean5.1efficient,3.4standard,withboundednoise;setpointmean25.5°C.
RoofU means2.8/1.5/.55andwallU2.1/1.45/.75byinsulation;independent/rowroof fullyexposed,oneof4apartments exposed.
Windowratio mean.23;SHGCmean.43double/.75single;shading=.9×Beta(2,3). Fans correlatearea/29;35%mean30W,others67W.
Fan hoursmean8inBengaluru/Pune,12elsewhere;lightinghoursmean4.5. LED/controls correlateinsulation/cooling.
Appliance kWh/day=(1+.62×occupants+.012×area)×mean-one lognormal(log-sigma.17),bounded.5–12.
Water systems geyser/solar/heat-pump/none probabilities.55/.13/.04/.28;litres varycity/heaterpresence.
PNGprobability.25Delhi/Mumbai/Pune,.07elsewhere;induction.15,remainingLPG. Availability-inspired demo probabilities,not surveyestimates.
Roofaccess/property constrain PVsampling; solar_kw never enters demand-model X. Exact bounded draws are inspectable in generate_dataset.

## Label rules and accounting

Shared expected_end_uses computes physical mean demand(beforePV),LPGinputenergy,PNGinputenergy from documented assumptions.
Household label=physicalmean×sharedgroupnoise×independenthouseholdnoise,allmean-one lognormal.
Sharedlogsigmas.08electric/.07cooking;individualsigmas.10electric/.12cooking. Absentfuelsremainexactzero.
These invented behavior/measurement distributions are not measured Indian uncertainty benchmarks.
Reference_* columns expose means but never enter X;IDs,origin,labels,postsolarimports,referencecolumnsareexcluded.
Engineering features add only input-derived weather(CDH,GHI,PVyield)andphysicsmean estimates.
electricity_balance(home,observeddemand) derives imports,self-use,generation,exports, preserving bothenergybalances.
LPG and PNG remain separate;annual_gas_kwh compatibility=sumLPG+PNG in common kWhinputenergy. No saleslabels/valueupliftfabricated.

## Evaluation

Groupdisjoint50/15/15/20train/validation/calibration/test. Frozen testgroups keyed exactdatasetSHA256.
Trainingalonefitscandidates/preprocessing;validationaloneselects;independentcalibrationestablishes90%relativeconformalranges;
testreportsMAE/RMSE/R²,WAPE,activefuelcoverage/width,subgroups,stress. Constant-targetR²andzero-denominatorWAPEarenull.
Calibrationusesone label-independentrandomrepresentativepergroup;exchangeabilityofindependentgroupsrequired.
Row/subgroup/driftcoverageisempirical,notguaranteed. Physicsbaselineeligible,andlikelybestbecauseitisthegeneratorconditionalmean.
Selectedandbestlearnedpipelinearepreserved;noMLwinisforced. Stressreferencesassumedphysicsor35%unobservedusageshift,notrealcausallabels.

## External CSV

train.py --data-csv observations.csv --provenance-json provenance.json requires explicitfullannualobservations.
Columns:home_id(uniquerow),group_id(sharedhousehold/building),allFEATURES,andallthreeTARGETS.
Imports-onlycannotreplaceelectricitydemand;missingrequiredphysicalfeaturesarerejectedratherthaninvented.
Manifest:data_kind(measured|synthetic),source,license,units(kWh/year),geographic_scope.
Measuredalso:measurement_start/endcover365/366days,target_definitionsforallTARGETS.Synthetic:label_rule_version.
Declaredprovenanceisnotauditverification.Defaultmodelsremainsyntheticuntilreplacedwithsuitablelicensedmeasureddata.
Auditrepresentativeness,leakage,climate/yeartransfer,calibration,subgroupsandretrofitcausalitybeforerealdecisionuse.
