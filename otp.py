from app.utils.utils import send_otp


async def send_one_time_password():
    await send_otp(
        name="John Doe",
        email="johndoe@example.com",
        phone="09074345335"
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(send_one_time_password())

"""


CBN Code	Bank Name
044	Access Bank Nigeria Plc Or Diamond Bank Plc
050	Ecobank Nigeria
084	Enterprise Bank Plc
070	Fidelity Bank Plc
011	First Bank of Nigeria Plc
214	First City Monument Bank
058	Guaranty Trust Bank Plc
301	Jaiz Bank
082	Keystone Bank Ltd
014	Mainstreet Bank Plc
076	Skye Bank Plc
039	Stanbic IBTC Plc
232	Sterling Bank Plc
032	Union Bank Nigeria Plc
033	United Bank for Africa Plc
215	Unity Bank Plc
035	WEMA Bank Plc
057	Zenith Bank International
101	Providus Bank
104	PARALLEX BANK LIMITED
303	LOTUS BANK LIMITED
105	PREMIUM TRUST BANK LTD
106	SIGNATURE BANK LTD
103	GLOBUS BANK
102	TITAN TRUST BANK
067	Polaris Bank
107	OPTIMUS BANK LTD
068	Standard Chartered Bank
100	Suntrust Bank
"""

data = {
  "status": "success",
  "message": "Banks fetched successfully",
  "data": [
    {
      "id": 132,
      "code": "560",
      "name": "Page MFBank",
      "provider_type": "bank"
    },
    {
      "id": 133,
      "code": "304",
      "name": "Stanbic Mobile Money",
      "provider_type": "bank"
    },
    {
      "id": 134,
      "code": "308",
      "name": "FortisMobile",
      "provider_type": "bank"
    },
    {
      "id": 135,
      "code": "328",
      "name": "TagPay",
      "provider_type": "bank"
    },
    {
      "id": 136,
      "code": "309",
      "name": "FBNMobile",
      "provider_type": "bank"
    },
    {
      "id": 137,
      "code": "011",
      "name": "First Bank of Nigeria",
      "provider_type": "bank"
    },
    {
      "id": 138,
      "code": "326",
      "name": "Sterling Mobile",
      "provider_type": "bank"
    },
    {
      "id": 139,
      "code": "990",
      "name": "Omoluabi Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 140,
      "code": "311",
      "name": "ReadyCash (Parkway)",
      "provider_type": "bank"
    },
    {
      "id": 141,
      "code": "057",
      "name": "Zenith Bank",
      "provider_type": "bank"
    },
    {
      "id": 142,
      "code": "068",
      "name": "Standard Chartered Bank",
      "provider_type": "bank"
    },
    {
      "id": 143,
      "code": "306",
      "name": "eTranzact",
      "provider_type": "bank"
    },
    {
      "id": 144,
      "code": "070",
      "name": "Fidelity Bank",
      "provider_type": "bank"
    },
    {
      "id": 145,
      "code": "023",
      "name": "CitiBank",
      "provider_type": "bank"
    },
    {
      "id": 146,
      "code": "215",
      "name": "Unity Bank",
      "provider_type": "bank"
    },
    {
      "id": 147,
      "code": "323",
      "name": "Access Money",
      "provider_type": "bank"
    },
    {
      "id": 148,
      "code": "302",
      "name": "Eartholeum",
      "provider_type": "bank"
    },
    {
      "id": 149,
      "code": "324",
      "name": "Hedonmark",
      "provider_type": "bank"
    },
    {
      "id": 150,
      "code": "325",
      "name": "MoneyBox",
      "provider_type": "bank"
    },
    {
      "id": 151,
      "code": "301",
      "name": "JAIZ Bank",
      "provider_type": "bank"
    },
    {
      "id": 152,
      "code": "050",
      "name": "Ecobank Plc",
      "provider_type": "bank"
    },
    {
      "id": 153,
      "code": "307",
      "name": "EcoMobile",
      "provider_type": "bank"
    },
    {
      "id": 154,
      "code": "318",
      "name": "Fidelity Mobile",
      "provider_type": "bank"
    },
    {
      "id": 155,
      "code": "319",
      "name": "TeasyMobile",
      "provider_type": "bank"
    },
    {
      "id": 156,
      "code": "999",
      "name": "NIP Virtual Bank",
      "provider_type": "bank"
    },
    {
      "id": 157,
      "code": "320",
      "name": "VTNetworks",
      "provider_type": "bank"
    },
    {
      "id": 158,
      "code": "221",
      "name": "Stanbic IBTC Bank",
      "provider_type": "bank"
    },
    {
      "id": 159,
      "code": "501",
      "name": "Fortis Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 160,
      "code": "329",
      "name": "PayAttitude Online",
      "provider_type": "bank"
    },
    {
      "id": 161,
      "code": "322",
      "name": "ZenithMobile",
      "provider_type": "bank"
    },
    {
      "id": 162,
      "code": "303",
      "name": "ChamsMobile",
      "provider_type": "bank"
    },
    {
      "id": 163,
      "code": "403",
      "name": "SafeTrust Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 164,
      "code": "551",
      "name": "Covenant Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 165,
      "code": "415",
      "name": "Imperial Homes Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 166,
      "code": "552",
      "name": "NPF MicroFinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 167,
      "code": "526",
      "name": "Parralex",
      "provider_type": "bank"
    },
    {
      "id": 168,
      "code": "035",
      "name": "Wema Bank",
      "provider_type": "bank"
    },
    {
      "id": 169,
      "code": "084",
      "name": "Enterprise Bank",
      "provider_type": "bank"
    },
    {
      "id": 170,
      "code": "063",
      "name": "Diamond Bank",
      "provider_type": "bank"
    },
    {
      "id": 171,
      "code": "305",
      "name": "Paycom",
      "provider_type": "bank"
    },
    {
      "id": 172,
      "code": "100",
      "name": "SunTrust Bank",
      "provider_type": "bank"
    },
    {
      "id": 173,
      "code": "317",
      "name": "Cellulant",
      "provider_type": "bank"
    },
    {
      "id": 174,
      "code": "401",
      "name": "ASO Savings and & Loans",
      "provider_type": "bank"
    },
    {
      "id": 175,
      "code": "030",
      "name": "Heritage",
      "provider_type": "bank"
    },
    {
      "id": 176,
      "code": "402",
      "name": "Jubilee Life Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 177,
      "code": "058",
      "name": "GTBank Plc",
      "provider_type": "bank"
    },
    {
      "id": 178,
      "code": "032",
      "name": "Union Bank",
      "provider_type": "bank"
    },
    {
      "id": 179,
      "code": "232",
      "name": "Sterling Bank",
      "provider_type": "bank"
    },
    {
      "id": 180,
      "code": "076",
      "name": "Polaris Bank",
      "provider_type": "bank"
    },
    {
      "id": 181,
      "code": "082",
      "name": "Keystone Bank",
      "provider_type": "bank"
    },
    {
      "id": 182,
      "code": "327",
      "name": "Pagatech",
      "provider_type": "bank"
    },
    {
      "id": 183,
      "code": "559",
      "name": "Coronation Merchant Bank",
      "provider_type": "bank"
    },
    {
      "id": 184,
      "code": "601",
      "name": "FSDH",
      "provider_type": "bank"
    },
    {
      "id": 185,
      "code": "313",
      "name": "Mkudi",
      "provider_type": "bank"
    },
    {
      "id": 186,
      "code": "214",
      "name": "First City Monument Bank",
      "provider_type": "bank"
    },
    {
      "id": 187,
      "code": "314",
      "name": "FET",
      "provider_type": "bank"
    },
    {
      "id": 188,
      "code": "523",
      "name": "Trustbond",
      "provider_type": "bank"
    },
    {
      "id": 189,
      "code": "315",
      "name": "GTMobile",
      "provider_type": "bank"
    },
    {
      "id": 190,
      "code": "033",
      "name": "United Bank for Africa",
      "provider_type": "bank"
    },
    {
      "id": 191,
      "code": "044",
      "name": "Access Bank",
      "provider_type": "bank"
    },
    {
      "id": 567,
      "code": "90115",
      "name": "TCF MFB",
      "provider_type": "bank"
    },
    {
      "id": 1413,
      "code": "090175",
      "name": "Test bank",
      "provider_type": "bank"
    },
    {
      "id": 1731,
      "code": "103",
      "name": "Globus Bank",
      "provider_type": "bank"
    },
    {
      "id": 1800,
      "code": "000019",
      "name": "Enterprise Bank",
      "provider_type": "bank"
    },
    {
      "id": 1801,
      "code": "000025",
      "name": "Titan Trust Bank",
      "provider_type": "bank"
    },
    {
      "id": 1802,
      "code": "000026",
      "name": "Taj Bank Limited",
      "provider_type": "bank"
    },
    {
      "id": 1803,
      "code": "000028",
      "name": "Central Bank Of Nigeria",
      "provider_type": "bank"
    },
    {
      "id": 1804,
      "code": "000029",
      "name": "Lotus Bank",
      "provider_type": "bank"
    },
    {
      "id": 1805,
      "code": "000030",
      "name": "Parallex Bank",
      "provider_type": "bank"
    },
    {
      "id": 1806,
      "code": "000031",
      "name": "PremiumTrust Bank",
      "provider_type": "bank"
    },
    {
      "id": 1807,
      "code": "000033",
      "name": "ENaira",
      "provider_type": "bank"
    },
    {
      "id": 1808,
      "code": "000034",
      "name": "SIGNATURE BANK",
      "provider_type": "bank"
    },
    {
      "id": 1809,
      "code": "000036",
      "name": "Optimus Bank",
      "provider_type": "bank"
    },
    {
      "id": 1810,
      "code": "050001",
      "name": "County Finance Ltd",
      "provider_type": "bank"
    },
    {
      "id": 1811,
      "code": "050002",
      "name": "Fewchore Finance Company Limited",
      "provider_type": "bank"
    },
    {
      "id": 1812,
      "code": "050003",
      "name": "Sagegrey Finance Limited",
      "provider_type": "bank"
    },
    {
      "id": 1813,
      "code": "050004",
      "name": "Newedge Finance Ltd",
      "provider_type": "bank"
    },
    {
      "id": 1814,
      "code": "050005",
      "name": "Aaa Finance",
      "provider_type": "bank"
    },
    {
      "id": 1815,
      "code": "050006",
      "name": "Branch International Financial Services",
      "provider_type": "bank"
    },
    {
      "id": 1816,
      "code": "050007",
      "name": "Tekla Finance Ltd",
      "provider_type": "bank"
    },
    {
      "id": 1817,
      "code": "050008",
      "name": "SIMPLE FINANCE LIMITED",
      "provider_type": "bank"
    },
    {
      "id": 1818,
      "code": "050009",
      "name": "FAST CREDIT",
      "provider_type": "bank"
    },
    {
      "id": 1819,
      "code": "050010",
      "name": "FUNDQUEST FINANCIAL SERVICES LTD",
      "provider_type": "bank"
    },
    {
      "id": 1820,
      "code": "050012",
      "name": "Enco Finance",
      "provider_type": "bank"
    },
    {
      "id": 1821,
      "code": "050013",
      "name": "Dignity Finance",
      "provider_type": "bank"
    },
    {
      "id": 1822,
      "code": "050014",
      "name": "TRINITY FINANCIAL SERVICES LIMITED",
      "provider_type": "bank"
    },
    {
      "id": 1823,
      "code": "060001",
      "name": "Coronation Merchant Bank",
      "provider_type": "bank"
    },
    {
      "id": 1824,
      "code": "060002",
      "name": "FBNQUEST Merchant Bank",
      "provider_type": "bank"
    },
    {
      "id": 1825,
      "code": "060003",
      "name": "Nova Merchant Bank",
      "provider_type": "bank"
    },
    {
      "id": 1826,
      "code": "060004",
      "name": "Greenwich Merchant Bank",
      "provider_type": "bank"
    },
    {
      "id": 1827,
      "code": "070001",
      "name": "NPF MicroFinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1828,
      "code": "070002",
      "name": "Fortis Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1829,
      "code": "070006",
      "name": "Covenant Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1830,
      "code": "070007",
      "name": "Omoluabi savings and loans",
      "provider_type": "bank"
    },
    {
      "id": 1831,
      "code": "070008",
      "name": "Page Financials",
      "provider_type": "bank"
    },
    {
      "id": 1832,
      "code": "070009",
      "name": "Gateway Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1833,
      "code": "070010",
      "name": "Abbey Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1834,
      "code": "070011",
      "name": "Refuge Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1835,
      "code": "070012",
      "name": "Lagos Building Investment Company",
      "provider_type": "bank"
    },
    {
      "id": 1836,
      "code": "070013",
      "name": "Platinum Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1837,
      "code": "070014",
      "name": "First Generation Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1838,
      "code": "070015",
      "name": "Brent Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1839,
      "code": "070016",
      "name": "Infinity Trust Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1840,
      "code": "070017",
      "name": "Haggai Mortgage Bank Limited",
      "provider_type": "bank"
    },
    {
      "id": 1841,
      "code": "070019",
      "name": "Mayfresh Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1842,
      "code": "070021",
      "name": "Coop Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1843,
      "code": "070022",
      "name": "Stb Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1844,
      "code": "070023",
      "name": "Delta Trust Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1845,
      "code": "070024",
      "name": "Homebase Mortgage",
      "provider_type": "bank"
    },
    {
      "id": 1846,
      "code": "070025",
      "name": "Akwa Savings & Loans Limited",
      "provider_type": "bank"
    },
    {
      "id": 1847,
      "code": "070026",
      "name": "Fha Mortgage Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 1848,
      "code": "080002",
      "name": "Tajwallet",
      "provider_type": "bank"
    },
    {
      "id": 1849,
      "code": "090001",
      "name": "ASOSavings & Loans",
      "provider_type": "bank"
    },
    {
      "id": 1850,
      "code": "090003",
      "name": "Jubilee-Life Mortgage  Bank",
      "provider_type": "bank"
    },
    {
      "id": 1851,
      "code": "090004",
      "name": "Parralex Microfinance bank",
      "provider_type": "bank"
    },
    {
      "id": 1852,
      "code": "090005",
      "name": "Trustbond Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 1853,
      "code": "090006",
      "name": "SafeTrust ",
      "provider_type": "bank"
    },
    {
      "id": 1854,
      "code": "090097",
      "name": "Ekondo MFB",
      "provider_type": "bank"
    },
    {
      "id": 1855,
      "code": "090107",
      "name": "FBN Mortgages Limited",
      "provider_type": "bank"
    },
    {
      "id": 1856,
      "code": "090108",
      "name": "New Prudential Bank",
      "provider_type": "bank"
    },
    {
      "id": 1857,
      "code": "090110",
      "name": "VFD Micro Finance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1858,
      "code": "090112",
      "name": "Seed Capital Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1859,
      "code": "090113",
      "name": "Microvis Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1860,
      "code": "090114",
      "name": "Empire trust MFB",
      "provider_type": "bank"
    },
    {
      "id": 1861,
      "code": "090115",
      "name": "TCF MFB",
      "provider_type": "bank"
    },
    {
      "id": 1862,
      "code": "090116",
      "name": "AMML MFB",
      "provider_type": "bank"
    },
    {
      "id": 1863,
      "code": "090117",
      "name": "Boctrust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1864,
      "code": "090118",
      "name": "IBILE Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1865,
      "code": "090119",
      "name": "Ohafia Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1866,
      "code": "090120",
      "name": "Wetland Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1867,
      "code": "090121",
      "name": "Hasal Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1868,
      "code": "090122",
      "name": "Gowans Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1869,
      "code": "090123",
      "name": "Verite Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1870,
      "code": "090124",
      "name": "Xslnce Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1871,
      "code": "090125",
      "name": "Regent Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1872,
      "code": "090126",
      "name": "Fidfund Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1873,
      "code": "090127",
      "name": "BC Kash Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1874,
      "code": "090128",
      "name": "Ndiorah Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1875,
      "code": "090129",
      "name": "Money Trust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1876,
      "code": "090130",
      "name": "Consumer Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1877,
      "code": "090131",
      "name": "Allworkers Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1878,
      "code": "090132",
      "name": "Richway Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1879,
      "code": "090133",
      "name": " AL-Barakah Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1880,
      "code": "090134",
      "name": "Accion Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1881,
      "code": "090135",
      "name": "Personal Trust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1882,
      "code": "090136",
      "name": "Baobab Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1883,
      "code": "090137",
      "name": "PecanTrust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1884,
      "code": "090138",
      "name": "Royal Exchange Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1885,
      "code": "090139",
      "name": "Visa Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1886,
      "code": "090140",
      "name": "Sagamu Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1887,
      "code": "090141",
      "name": "Chikum Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1888,
      "code": "090142",
      "name": "Yes Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1889,
      "code": "090143",
      "name": "Apeks Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1890,
      "code": "090144",
      "name": "CIT Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1891,
      "code": "090145",
      "name": "Fullrange Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1892,
      "code": "090146",
      "name": "Trident Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1893,
      "code": "090147",
      "name": "Hackman Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1894,
      "code": "090148",
      "name": "Bowen Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1895,
      "code": "090149",
      "name": "IRL Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1896,
      "code": "090150",
      "name": "Virtue Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1897,
      "code": "090151",
      "name": "Mutual Trust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1898,
      "code": "090152",
      "name": "Nagarta Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1899,
      "code": "090153",
      "name": "FFS Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1900,
      "code": "090154",
      "name": "CEMCS Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1901,
      "code": "090155",
      "name": "La  Fayette Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1902,
      "code": "090156",
      "name": "e-Barcs Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1903,
      "code": "090157",
      "name": "Infinity Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1904,
      "code": "090158",
      "name": "Futo Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1905,
      "code": "090159",
      "name": "Credit Afrique Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1906,
      "code": "090160",
      "name": "Addosser Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1907,
      "code": "090161",
      "name": "Okpoga Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1908,
      "code": "090162",
      "name": "Stanford Microfinance Bak",
      "provider_type": "bank"
    },
    {
      "id": 1909,
      "code": "090163",
      "name": "First Multiple Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1910,
      "code": "090164",
      "name": "First Royal Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1911,
      "code": "090165",
      "name": "Petra Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1912,
      "code": "090166",
      "name": "Eso-E Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1913,
      "code": "090167",
      "name": "Daylight Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1914,
      "code": "090168",
      "name": "Gashua Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1915,
      "code": "090169",
      "name": "Alpha Kapital Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1916,
      "code": "090170",
      "name": "Rahama Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1917,
      "code": "090171",
      "name": "Mainstreet Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1918,
      "code": "090172",
      "name": "Astrapolaris Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1919,
      "code": "090173",
      "name": "Reliance Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1920,
      "code": "090174",
      "name": "Malachy Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1921,
      "code": "090176",
      "name": "Bosak Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1922,
      "code": "090177",
      "name": "Lapo Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1923,
      "code": "090178",
      "name": "GreenBank Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1924,
      "code": "090179",
      "name": "FAST Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1925,
      "code": "090180",
      "name": "AMJU Unique Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1926,
      "code": "090181",
      "name": "Balogun Fulani  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1927,
      "code": "090182",
      "name": "Standard Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1928,
      "code": "090186",
      "name": "Girei Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1929,
      "code": "090188",
      "name": "Baines Credit Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1930,
      "code": "090189",
      "name": "Esan Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1931,
      "code": "090190",
      "name": "Mutual Benefits Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1932,
      "code": "090191",
      "name": "KCMB Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1933,
      "code": "090192",
      "name": "Midland Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1934,
      "code": "090193",
      "name": "Unical Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1935,
      "code": "090194",
      "name": "NIRSAL Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1936,
      "code": "090195",
      "name": "Grooming Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1937,
      "code": "090196",
      "name": "Pennywise Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1938,
      "code": "090197",
      "name": "ABU Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1939,
      "code": "090198",
      "name": "RenMoney Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1940,
      "code": "090201",
      "name": "Xpress Payments",
      "provider_type": "bank"
    },
    {
      "id": 1941,
      "code": "090202",
      "name": "Accelerex Network",
      "provider_type": "bank"
    },
    {
      "id": 1942,
      "code": "090205",
      "name": "New Dawn Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1943,
      "code": "090211",
      "name": "Itex Integrated Services Limited",
      "provider_type": "bank"
    },
    {
      "id": 1944,
      "code": "090251",
      "name": "UNN MFB",
      "provider_type": "bank"
    },
    {
      "id": 1945,
      "code": "090252",
      "name": "Yobe Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1946,
      "code": "090254",
      "name": "Coalcamp Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1947,
      "code": "090258",
      "name": "Imo State Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1948,
      "code": "090259",
      "name": "Alekun Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1949,
      "code": "090260",
      "name": "Above Only Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1950,
      "code": "090261",
      "name": "Quickfund Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1951,
      "code": "090262",
      "name": "Stellas Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1952,
      "code": "090263",
      "name": "Navy Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1953,
      "code": "090264",
      "name": "Auchi Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1954,
      "code": "090265",
      "name": "Lovonus Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1955,
      "code": "090266",
      "name": "Uniben Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1956,
      "code": "090267",
      "name": "Kuda",
      "provider_type": "bank"
    },
    {
      "id": 1957,
      "code": "090268",
      "name": "Adeyemi College Staff Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1958,
      "code": "090269",
      "name": "Greenville Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1959,
      "code": "090270",
      "name": "AB Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1960,
      "code": "090271",
      "name": "Lavender Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1961,
      "code": "090272",
      "name": "Olabisi Onabanjo University Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1962,
      "code": "090273",
      "name": "Emeralds Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1963,
      "code": "090274",
      "name": "Prestige Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1964,
      "code": "090275",
      "name": "Meridian Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1965,
      "code": "090276",
      "name": "Trustfund Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1966,
      "code": "090277",
      "name": "Al-Hayat Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1967,
      "code": "090278",
      "name": "Glory Microfinance Bank ",
      "provider_type": "bank"
    },
    {
      "id": 1968,
      "code": "090279",
      "name": "Ikire Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1969,
      "code": "090280",
      "name": "Megapraise Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1970,
      "code": "090281",
      "name": "Mint-Finex MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 1971,
      "code": "090282",
      "name": "Arise Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1972,
      "code": "090283",
      "name": "Thrive Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1973,
      "code": "090285",
      "name": "First Option Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1974,
      "code": "090286",
      "name": "Safe Haven MFB",
      "provider_type": "bank"
    },
    {
      "id": 1975,
      "code": "090287",
      "name": "Assets Matrix Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1976,
      "code": "090289",
      "name": "Pillar Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1977,
      "code": "090290",
      "name": "Fct Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1978,
      "code": "090291",
      "name": "Halacredit Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1979,
      "code": "090292",
      "name": "Afekhafe Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1980,
      "code": "090293",
      "name": "Brethren Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1981,
      "code": "090294",
      "name": "Eagle Flight Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1982,
      "code": "090295",
      "name": "Omiye Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1983,
      "code": "090296",
      "name": "Polyuwanna Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1984,
      "code": "090297",
      "name": "Alert Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1985,
      "code": "090298",
      "name": "Federalpoly Nasarawamfb",
      "provider_type": "bank"
    },
    {
      "id": 1986,
      "code": "090299",
      "name": "Kontagora Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1987,
      "code": "090302",
      "name": "Sunbeam Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1988,
      "code": "090303",
      "name": "Purplemoney Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1989,
      "code": "090304",
      "name": "Evangel Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1990,
      "code": "090305",
      "name": "Sulsap Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1991,
      "code": "090307",
      "name": "Aramoko Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1992,
      "code": "090308",
      "name": "Brightway Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1993,
      "code": "090310",
      "name": "Edfin Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1994,
      "code": "090315",
      "name": "U And C Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1995,
      "code": "090316",
      "name": "Bayero Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1996,
      "code": "090317",
      "name": "PatrickGold Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1997,
      "code": "090318",
      "name": "Federal University Dutse  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1998,
      "code": "090319",
      "name": "Bonghe Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 1999,
      "code": "090320",
      "name": "Kadpoly Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2000,
      "code": "090321",
      "name": "Mayfair  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2001,
      "code": "090322",
      "name": "Rephidim Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2002,
      "code": "090323",
      "name": "Mainland Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2003,
      "code": "090324",
      "name": "Ikenne Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2004,
      "code": "090325",
      "name": "Sparkle",
      "provider_type": "bank"
    },
    {
      "id": 2005,
      "code": "090326",
      "name": "Balogun Gambari Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2006,
      "code": "090327",
      "name": "Trust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2007,
      "code": "090328",
      "name": "Eyowo MFB",
      "provider_type": "bank"
    },
    {
      "id": 2008,
      "code": "090329",
      "name": "Neptune Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2009,
      "code": "090330",
      "name": "Fame Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2010,
      "code": "090331",
      "name": "Unaab Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2011,
      "code": "090332",
      "name": "Evergreen Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2012,
      "code": "090333",
      "name": "Oche Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2013,
      "code": "090335",
      "name": "Grant MF Bank",
      "provider_type": "bank"
    },
    {
      "id": 2014,
      "code": "090336",
      "name": "Bipc Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2015,
      "code": "090337",
      "name": "Iyeru Okin Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2016,
      "code": "090338",
      "name": "Uniuyo Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2017,
      "code": "090340",
      "name": "Stockcorp  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2018,
      "code": "090341",
      "name": "Unilorin Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2019,
      "code": "090343",
      "name": "Citizen Trust Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2020,
      "code": "090345",
      "name": "Oau Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2021,
      "code": "090349",
      "name": "Nasarawa Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2022,
      "code": "090350",
      "name": "Illorin Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2023,
      "code": "090352",
      "name": "Jessefield Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2024,
      "code": "090353",
      "name": "Isuofia Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2025,
      "code": "090360",
      "name": "Cashconnect   Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2026,
      "code": "090362",
      "name": "Molusi Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2027,
      "code": "090363",
      "name": "Headway Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2028,
      "code": "090364",
      "name": "Nuture Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2029,
      "code": "090365",
      "name": "Corestep Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2030,
      "code": "090366",
      "name": "Firmus MFB",
      "provider_type": "bank"
    },
    {
      "id": 2031,
      "code": "090369",
      "name": "Seedvest Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2032,
      "code": "090370",
      "name": "Ilasan Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2033,
      "code": "090371",
      "name": "Agosasa Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2034,
      "code": "090372",
      "name": "Legend Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2035,
      "code": "090373",
      "name": "Tf Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2036,
      "code": "090374",
      "name": "Coastline Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2037,
      "code": "090376",
      "name": "Apple  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2038,
      "code": "090377",
      "name": "Isaleoyo Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2039,
      "code": "090378",
      "name": "New Golden Pastures Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2040,
      "code": "090379",
      "name": "Peniel Micorfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2041,
      "code": "090380",
      "name": "Kredi Money Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2042,
      "code": "090383",
      "name": "Manny Microfinance bank",
      "provider_type": "bank"
    },
    {
      "id": 2043,
      "code": "090385",
      "name": "Gti  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2044,
      "code": "090386",
      "name": "Interland Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2045,
      "code": "090389",
      "name": "Ek-Reliable Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2046,
      "code": "090390",
      "name": "Parkway Mf Bank",
      "provider_type": "bank"
    },
    {
      "id": 2047,
      "code": "090391",
      "name": "Davodani  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2048,
      "code": "090392",
      "name": "Mozfin Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2049,
      "code": "090393",
      "name": "BRIDGEWAY MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 2050,
      "code": "090394",
      "name": "Amac Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2051,
      "code": "090395",
      "name": "Borgu Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2052,
      "code": "090396",
      "name": "Oscotech Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2053,
      "code": "090397",
      "name": "Chanelle Bank",
      "provider_type": "bank"
    },
    {
      "id": 2054,
      "code": "090398",
      "name": "Federal Polytechnic Nekede Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2055,
      "code": "090399",
      "name": "Nwannegadi Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2056,
      "code": "090400",
      "name": "Finca Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2057,
      "code": "090401",
      "name": "Shepherd Trust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2058,
      "code": "090402",
      "name": "Peace Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2059,
      "code": "090403",
      "name": "Uda Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2060,
      "code": "090404",
      "name": "Olowolagba Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2061,
      "code": "090405",
      "name": "Moniepoint Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2062,
      "code": "090406",
      "name": "Business Support Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2063,
      "code": "090408",
      "name": "Gmb Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2064,
      "code": "090409",
      "name": "Fcmb Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2065,
      "code": "090410",
      "name": "Maritime Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2066,
      "code": "090411",
      "name": "Giginya Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2067,
      "code": "090412",
      "name": "Preeminent Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2068,
      "code": "090413",
      "name": "Benysta Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2069,
      "code": "090414",
      "name": "Crutech  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2070,
      "code": "090415",
      "name": "Calabar Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2071,
      "code": "090416",
      "name": "Chibueze Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2072,
      "code": "090417",
      "name": "Imowo Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2073,
      "code": "090418",
      "name": "Highland Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2074,
      "code": "090419",
      "name": "Winview Bank",
      "provider_type": "bank"
    },
    {
      "id": 2075,
      "code": "090420",
      "name": "Letshego MFB",
      "provider_type": "bank"
    },
    {
      "id": 2076,
      "code": "090421",
      "name": "Izon Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2077,
      "code": "090422",
      "name": "Landgold  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2078,
      "code": "090423",
      "name": "MAUTECH Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2079,
      "code": "090424",
      "name": "Abucoop  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2080,
      "code": "090425",
      "name": "Banex Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2081,
      "code": "090426",
      "name": "Tangerine Bank",
      "provider_type": "bank"
    },
    {
      "id": 2082,
      "code": "090427",
      "name": "Ebsu Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2083,
      "code": "090428",
      "name": "Ishie  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2084,
      "code": "090429",
      "name": "Crossriver  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2085,
      "code": "090430",
      "name": "Ilora Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2086,
      "code": "090431",
      "name": "Bluewhales  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2087,
      "code": "090432",
      "name": "Memphis Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2088,
      "code": "090433",
      "name": "Rigo Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2089,
      "code": "090434",
      "name": "Insight Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2090,
      "code": "090435",
      "name": "Links Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2091,
      "code": "090436",
      "name": "Spectrum Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2092,
      "code": "090437",
      "name": "Oakland Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2093,
      "code": "090438",
      "name": "Futminna Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2094,
      "code": "090439",
      "name": "Ibeto  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2095,
      "code": "090440",
      "name": "Cherish Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2096,
      "code": "090441",
      "name": "Giwa Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2097,
      "code": "090443",
      "name": "Rima Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2098,
      "code": "090444",
      "name": "Boi Mf Bank",
      "provider_type": "bank"
    },
    {
      "id": 2099,
      "code": "090445",
      "name": "Capstone Mf Bank",
      "provider_type": "bank"
    },
    {
      "id": 2100,
      "code": "090446",
      "name": "Support Mf Bank",
      "provider_type": "bank"
    },
    {
      "id": 2101,
      "code": "090448",
      "name": "Moyofade Mf Bank",
      "provider_type": "bank"
    },
    {
      "id": 2102,
      "code": "090449",
      "name": "Sls  Mf Bank",
      "provider_type": "bank"
    },
    {
      "id": 2103,
      "code": "090450",
      "name": "Kwasu Mf Bank",
      "provider_type": "bank"
    },
    {
      "id": 2104,
      "code": "090451",
      "name": "Atbu  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2105,
      "code": "090452",
      "name": "Unilag  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2106,
      "code": "090453",
      "name": "Uzondu Mf Bank",
      "provider_type": "bank"
    },
    {
      "id": 2107,
      "code": "090454",
      "name": "Borstal Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2108,
      "code": "090455",
      "name": "MKOBO MICROFINANCE BANK LTD",
      "provider_type": "bank"
    },
    {
      "id": 2109,
      "code": "090456",
      "name": "Ospoly Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2110,
      "code": "090459",
      "name": "Nice Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2111,
      "code": "090460",
      "name": "Oluyole Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2112,
      "code": "090461",
      "name": "Uniibadan Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2113,
      "code": "090462",
      "name": "Monarch Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2114,
      "code": "090463",
      "name": "Rehoboth Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2115,
      "code": "090464",
      "name": "Unimaid Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2116,
      "code": "090465",
      "name": "Maintrust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2117,
      "code": "090466",
      "name": "Yct Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2118,
      "code": "090467",
      "name": "Good Neighbours Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2119,
      "code": "090468",
      "name": "Olofin Owena Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2120,
      "code": "090469",
      "name": "Aniocha Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2121,
      "code": "090470",
      "name": "DOT MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 2122,
      "code": "090471",
      "name": "Oluchukwu Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2123,
      "code": "090472",
      "name": "Caretaker Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2124,
      "code": "090473",
      "name": "Assets Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2125,
      "code": "090474",
      "name": "Verdant Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2126,
      "code": "090475",
      "name": "Giant Stride Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2127,
      "code": "090476",
      "name": "Anchorage Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2128,
      "code": "090477",
      "name": "Light Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2129,
      "code": "090478",
      "name": "Avuenegbe Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2130,
      "code": "090479",
      "name": "First Heritage Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2131,
      "code": "090480",
      "name": "Cintrust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2132,
      "code": "090481",
      "name": "Prisco  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2133,
      "code": "090482",
      "name": "FEDETH MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 2134,
      "code": "090483",
      "name": "Ada Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2135,
      "code": "090484",
      "name": "Garki Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2136,
      "code": "090485",
      "name": "Safegate Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2137,
      "code": "090486",
      "name": "Fortress Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2138,
      "code": "090487",
      "name": "Kingdom College  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2139,
      "code": "090488",
      "name": "Ibu-Aje Microfinance",
      "provider_type": "bank"
    },
    {
      "id": 2140,
      "code": "090489",
      "name": "Alvana Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2141,
      "code": "090490",
      "name": "Chukwunenye  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2142,
      "code": "090491",
      "name": "Nsuk  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2143,
      "code": "090492",
      "name": "Oraukwu  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2144,
      "code": "090493",
      "name": "Iperu Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2145,
      "code": "090494",
      "name": "Boji Boji Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2146,
      "code": "090495",
      "name": "GOODNEWS MFB",
      "provider_type": "bank"
    },
    {
      "id": 2147,
      "code": "090496",
      "name": "Radalpha Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2148,
      "code": "090497",
      "name": "Palmcoast Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2149,
      "code": "090498",
      "name": "Catland Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2150,
      "code": "090499",
      "name": "Pristine Divitis Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2151,
      "code": "090500",
      "name": "Gwong Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2152,
      "code": "090501",
      "name": "Boromu Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2153,
      "code": "090502",
      "name": "Shalom Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2154,
      "code": "090503",
      "name": "Projects Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2155,
      "code": "090504",
      "name": "Zikora Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2156,
      "code": "090505",
      "name": "Nigeria Prisonsmicrofinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2157,
      "code": "090506",
      "name": "Solid Allianze Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2158,
      "code": "090507",
      "name": "Fims Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2159,
      "code": "090508",
      "name": "Borno Renaissance Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2160,
      "code": "090509",
      "name": "Capitalmetriq Swift Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2161,
      "code": "090510",
      "name": "Umunnachi Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2162,
      "code": "090511",
      "name": "Cloverleaf  Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2163,
      "code": "090512",
      "name": "Bubayero Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2164,
      "code": "090513",
      "name": "Seap Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2165,
      "code": "090514",
      "name": "Umuchinemere Procredit Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2166,
      "code": "090515",
      "name": "Rima Growth Pathway Microfinance Bank ",
      "provider_type": "bank"
    },
    {
      "id": 2167,
      "code": "090516",
      "name": "Numo Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2168,
      "code": "090517",
      "name": "Uhuru Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2169,
      "code": "090518",
      "name": "Afemai Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2170,
      "code": "090519",
      "name": "Ibom Fadama Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2171,
      "code": "090520",
      "name": "Ic Globalmicrofinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2172,
      "code": "090521",
      "name": "Foresight Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2173,
      "code": "090523",
      "name": "Chase Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2174,
      "code": "090524",
      "name": "Solidrock Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2175,
      "code": "090525",
      "name": "Triple A Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2176,
      "code": "090526",
      "name": "Crescent Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2177,
      "code": "090527",
      "name": "Ojokoro Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2178,
      "code": "090528",
      "name": "Mgbidi Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2179,
      "code": "090529",
      "name": "Ampersand Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2180,
      "code": "090530",
      "name": "Confidence Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2181,
      "code": "090531",
      "name": "Aku Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2182,
      "code": "090532",
      "name": "Ibolo Micorfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2183,
      "code": "090534",
      "name": "Polyibadan Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2184,
      "code": "090535",
      "name": "Nkpolu-Ust Microfinance",
      "provider_type": "bank"
    },
    {
      "id": 2185,
      "code": "090536",
      "name": "Ikoyi-Osun Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2186,
      "code": "090537",
      "name": "Lobrem Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2187,
      "code": "090538",
      "name": "Blue Investments Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2188,
      "code": "090539",
      "name": "Enrich Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2189,
      "code": "090540",
      "name": "Aztec Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2190,
      "code": "090541",
      "name": "Excellent Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2191,
      "code": "090542",
      "name": "Otuo Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2192,
      "code": "090543",
      "name": "Iwoama Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2193,
      "code": "090544",
      "name": "Aspire Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2194,
      "code": "090545",
      "name": "Abulesoro Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2195,
      "code": "090546",
      "name": "Ijebu-Ife Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2196,
      "code": "090547",
      "name": "Rockshield Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2197,
      "code": "090548",
      "name": "Ally Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2198,
      "code": "090549",
      "name": "Kc Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2199,
      "code": "090550",
      "name": "Green Energy Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2200,
      "code": "090551",
      "name": "Fairmoney Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2201,
      "code": "090552",
      "name": "Ekimogun Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2202,
      "code": "090553",
      "name": "Consistent Trust Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2203,
      "code": "090554",
      "name": "Kayvee Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2204,
      "code": "090555",
      "name": "Bishopgate Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2205,
      "code": "090556",
      "name": "Egwafin Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2206,
      "code": "090557",
      "name": "Lifegate Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2207,
      "code": "090558",
      "name": "Shongom Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2208,
      "code": "090559",
      "name": "Shield Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2209,
      "code": "090560",
      "name": "TANADI MFB (CRUST)",
      "provider_type": "bank"
    },
    {
      "id": 2210,
      "code": "090561",
      "name": "Akuchukwu Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2211,
      "code": "090562",
      "name": "Cedar Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2212,
      "code": "090563",
      "name": "Balera Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2213,
      "code": "090564",
      "name": "Supreme Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2214,
      "code": "090565",
      "name": "Oke-Aro Oredegbe Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2215,
      "code": "090566",
      "name": "Okuku Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2216,
      "code": "090567",
      "name": "Orokam Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2217,
      "code": "090568",
      "name": "Broadview Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2218,
      "code": "090569",
      "name": "Qube Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2219,
      "code": "090570",
      "name": "Iyamoye Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2220,
      "code": "090571",
      "name": "Ilaro Poly Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2221,
      "code": "090572",
      "name": "Ewt Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2222,
      "code": "090573",
      "name": "Snow Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2223,
      "code": "090574",
      "name": "GOLDMAN MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 2224,
      "code": "090575",
      "name": "Firstmidas Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2225,
      "code": "090576",
      "name": "Octopus Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2226,
      "code": "090578",
      "name": "Iwade Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2227,
      "code": "090579",
      "name": "Gbede Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2228,
      "code": "090580",
      "name": "Otech Microfinance Bank Ltd",
      "provider_type": "bank"
    },
    {
      "id": 2229,
      "code": "090581",
      "name": "BANC CORP MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 2230,
      "code": "090583",
      "name": "STATESIDE MFB",
      "provider_type": "bank"
    },
    {
      "id": 2231,
      "code": "090584",
      "name": "ISLAND MICROFINANCE BANK ",
      "provider_type": "bank"
    },
    {
      "id": 2232,
      "code": "090586",
      "name": "GOMBE MICROFINANCE BANK LTD",
      "provider_type": "bank"
    },
    {
      "id": 2233,
      "code": "090587",
      "name": "Microbiz Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2234,
      "code": "090588",
      "name": "Orisun MFB",
      "provider_type": "bank"
    },
    {
      "id": 2235,
      "code": "090589",
      "name": "Mercury MFB",
      "provider_type": "bank"
    },
    {
      "id": 2236,
      "code": "090590",
      "name": "WAYA MICROFINANCE BANK LTD",
      "provider_type": "bank"
    },
    {
      "id": 2237,
      "code": "090591",
      "name": "Gabsyn Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2238,
      "code": "090592",
      "name": "KANO POLY MFB",
      "provider_type": "bank"
    },
    {
      "id": 2239,
      "code": "090593",
      "name": "TASUED MICROFINANCE BANK LTD",
      "provider_type": "bank"
    },
    {
      "id": 2240,
      "code": "090598",
      "name": "IBA MFB ",
      "provider_type": "bank"
    },
    {
      "id": 2241,
      "code": "090599",
      "name": "Greenacres MFB",
      "provider_type": "bank"
    },
    {
      "id": 2242,
      "code": "090600",
      "name": "AVE MARIA MICROFINANCE BANK LTD",
      "provider_type": "bank"
    },
    {
      "id": 2243,
      "code": "090602",
      "name": "KENECHUKWU MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 2244,
      "code": "090603 ",
      "name": "Macrod MFB",
      "provider_type": "bank"
    },
    {
      "id": 2245,
      "code": "090606",
      "name": "KKU Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2246,
      "code": "090608",
      "name": "Akpo Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2247,
      "code": "090609",
      "name": "Ummah Microfinance Bank ",
      "provider_type": "bank"
    },
    {
      "id": 2248,
      "code": "090610",
      "name": "AMOYE MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 2249,
      "code": "090611",
      "name": "Creditville Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2250,
      "code": "090612",
      "name": "Medef Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2251,
      "code": "090613",
      "name": "Total Trust Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2252,
      "code": "090614",
      "name": "FLOURISH MFB",
      "provider_type": "bank"
    },
    {
      "id": 2253,
      "code": "090615",
      "name": "Beststar Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2254,
      "code": "090616",
      "name": "RAYYAN Microfinance Bank",
      "provider_type": "bank"
    },
    {
      "id": 2255,
      "code": "090620",
      "name": "Iyin Ekiti MFB",
      "provider_type": "bank"
    },
    {
      "id": 2256,
      "code": "090621",
      "name": "GIDAUNIYAR ALHERI MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 2257,
      "code": "090623",
      "name": "Mab Allianz MFB",
      "provider_type": "bank"
    },
    {
      "id": 2258,
      "code": "100001",
      "name": "FET",
      "provider_type": "bank"
    },
    {
      "id": 2259,
      "code": "100003",
      "name": "Parkway-ReadyCash",
      "provider_type": "bank"
    },
    {
      "id": 2260,
      "code": "100004",
      "name": "Opay",
      "provider_type": "bank"
    },
    {
      "id": 2261,
      "code": "100005",
      "name": "Cellulant",
      "provider_type": "bank"
    },
    {
      "id": 2262,
      "code": "100006",
      "name": "eTranzact",
      "provider_type": "bank"
    },
    {
      "id": 2263,
      "code": "100007",
      "name": "Stanbic IBTC @ease wallet",
      "provider_type": "bank"
    },
    {
      "id": 2264,
      "code": "100008",
      "name": "Ecobank Xpress Account",
      "provider_type": "bank"
    },
    {
      "id": 2265,
      "code": "100009",
      "name": "GTMobile",
      "provider_type": "bank"
    },
    {
      "id": 2266,
      "code": "100010",
      "name": "TeasyMobile",
      "provider_type": "bank"
    },
    {
      "id": 2267,
      "code": "100011",
      "name": "Mkudi",
      "provider_type": "bank"
    },
    {
      "id": 2268,
      "code": "100012",
      "name": "VTNetworks",
      "provider_type": "bank"
    },
    {
      "id": 2269,
      "code": "100013",
      "name": "AccessMobile",
      "provider_type": "bank"
    },
    {
      "id": 2270,
      "code": "100014",
      "name": "FBNMobile",
      "provider_type": "bank"
    },
    {
      "id": 2271,
      "code": "100015",
      "name": "Kegow",
      "provider_type": "bank"
    },
    {
      "id": 2272,
      "code": "100016",
      "name": "FortisMobile",
      "provider_type": "bank"
    },
    {
      "id": 2273,
      "code": "100017",
      "name": "Hedonmark",
      "provider_type": "bank"
    },
    {
      "id": 2274,
      "code": "100018",
      "name": "ZenithMobile",
      "provider_type": "bank"
    },
    {
      "id": 2275,
      "code": "100019",
      "name": "Fidelity Mobile",
      "provider_type": "bank"
    },
    {
      "id": 2276,
      "code": "100020",
      "name": "MoneyBox",
      "provider_type": "bank"
    },
    {
      "id": 2277,
      "code": "100021",
      "name": "Eartholeum",
      "provider_type": "bank"
    },
    {
      "id": 2278,
      "code": "100022",
      "name": "GoMoney",
      "provider_type": "bank"
    },
    {
      "id": 2279,
      "code": "100023",
      "name": "TagPay",
      "provider_type": "bank"
    },
    {
      "id": 2280,
      "code": "100024",
      "name": "Imperial Homes Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 2281,
      "code": "100025",
      "name": "Zinternet Nigera Limited",
      "provider_type": "bank"
    },
    {
      "id": 2282,
      "code": "100026",
      "name": "One Finance",
      "provider_type": "bank"
    },
    {
      "id": 2283,
      "code": "100027",
      "name": "Intellifin",
      "provider_type": "bank"
    },
    {
      "id": 2284,
      "code": "100028",
      "name": "AG Mortgage Bank",
      "provider_type": "bank"
    },
    {
      "id": 2285,
      "code": "100029",
      "name": "Innovectives Kesh",
      "provider_type": "bank"
    },
    {
      "id": 2286,
      "code": "100030",
      "name": "EcoMobile",
      "provider_type": "bank"
    },
    {
      "id": 2287,
      "code": "100031",
      "name": "FCMB Easy Account",
      "provider_type": "bank"
    },
    {
      "id": 2288,
      "code": "100032",
      "name": "Contec Global Infotech Limited (NowNow)",
      "provider_type": "bank"
    },
    {
      "id": 2289,
      "code": "100033",
      "name": "PALMPAY",
      "provider_type": "bank"
    },
    {
      "id": 2290,
      "code": "100034",
      "name": "Zwallet",
      "provider_type": "bank"
    },
    {
      "id": 2291,
      "code": "100035",
      "name": "M36",
      "provider_type": "bank"
    },
    {
      "id": 2292,
      "code": "100036",
      "name": "Kegow(Chamsmobile)",
      "provider_type": "bank"
    },
    {
      "id": 2293,
      "code": "100039",
      "name": "Titan-Paystack",
      "provider_type": "bank"
    },
    {
      "id": 2294,
      "code": "100052",
      "name": "Beta-Access Yello",
      "provider_type": "bank"
    },
    {
      "id": 2295,
      "code": "101",
      "name": "ProvidusBank PLC",
      "provider_type": "bank"
    },
    {
      "id": 2296,
      "code": "110001",
      "name": "PayAttitude Online",
      "provider_type": "bank"
    },
    {
      "id": 2297,
      "code": "110002",
      "name": "Flutterwave Technology Solutions Limited",
      "provider_type": "bank"
    },
    {
      "id": 2298,
      "code": "110003",
      "name": "Interswitch Limited",
      "provider_type": "bank"
    },
    {
      "id": 2299,
      "code": "110004",
      "name": "First Apple Limited",
      "provider_type": "bank"
    },
    {
      "id": 2300,
      "code": "110005",
      "name": "3Line Card Management Limited",
      "provider_type": "bank"
    },
    {
      "id": 2301,
      "code": "110006",
      "name": "Paystack Payments Limited",
      "provider_type": "bank"
    },
    {
      "id": 2302,
      "code": "110007",
      "name": "TeamApt",
      "provider_type": "bank"
    },
    {
      "id": 2303,
      "code": "110008",
      "name": "Kadick Integration Limited",
      "provider_type": "bank"
    },
    {
      "id": 2304,
      "code": "110009",
      "name": "Venture Garden Nigeria Limited",
      "provider_type": "bank"
    },
    {
      "id": 2305,
      "code": "110010",
      "name": "Interswitch Financial Inclusion Services (Ifis)",
      "provider_type": "bank"
    },
    {
      "id": 2306,
      "code": "110011",
      "name": "Arca Payments",
      "provider_type": "bank"
    },
    {
      "id": 2307,
      "code": "110012",
      "name": "Cellulant Pssp",
      "provider_type": "bank"
    },
    {
      "id": 2308,
      "code": "110013",
      "name": "Qr Payments",
      "provider_type": "bank"
    },
    {
      "id": 2309,
      "code": "110014",
      "name": "Cyberspace Limited",
      "provider_type": "bank"
    },
    {
      "id": 2310,
      "code": "110015",
      "name": "Vas2Nets Limited",
      "provider_type": "bank"
    },
    {
      "id": 2311,
      "code": "110017",
      "name": "Crowdforce",
      "provider_type": "bank"
    },
    {
      "id": 2312,
      "code": "110018",
      "name": "Microsystems Investment And Development Limited",
      "provider_type": "bank"
    },
    {
      "id": 2313,
      "code": "110019",
      "name": "Nibssussd Payments",
      "provider_type": "bank"
    },
    {
      "id": 2314,
      "code": "110021",
      "name": "Bud Infrastructure Limited",
      "provider_type": "bank"
    },
    {
      "id": 2315,
      "code": "110022",
      "name": "Koraypay",
      "provider_type": "bank"
    },
    {
      "id": 2316,
      "code": "110023",
      "name": "Capricorn Digital",
      "provider_type": "bank"
    },
    {
      "id": 2317,
      "code": "110024",
      "name": "Resident Fintech Limited",
      "provider_type": "bank"
    },
    {
      "id": 2318,
      "code": "110025",
      "name": "Netapps Technology Limited",
      "provider_type": "bank"
    },
    {
      "id": 2319,
      "code": "110026",
      "name": "Spay Business",
      "provider_type": "bank"
    },
    {
      "id": 2320,
      "code": "110027",
      "name": "Yello Digital Financial Services",
      "provider_type": "bank"
    },
    {
      "id": 2321,
      "code": "110028",
      "name": "Nomba Financial Services Limited",
      "provider_type": "bank"
    },
    {
      "id": 2322,
      "code": "110029",
      "name": "Woven Finance",
      "provider_type": "bank"
    },
    {
      "id": 2323,
      "code": "110044",
      "name": "Leadremit Limited",
      "provider_type": "bank"
    },
    {
      "id": 2324,
      "code": "120001",
      "name": "9 Payment Service Bank",
      "provider_type": "bank"
    },
    {
      "id": 2325,
      "code": "120002",
      "name": "Hopepsb",
      "provider_type": "bank"
    },
    {
      "id": 2326,
      "code": "120003",
      "name": "Momo Psb",
      "provider_type": "bank"
    },
    {
      "id": 2327,
      "code": "120004",
      "name": "Smartcash Payment Service Bank",
      "provider_type": "bank"
    },
    {
      "id": 2328,
      "code": "120005",
      "name": "Money Master Psb",
      "provider_type": "bank"
    },
    {
      "id": 2329,
      "code": "400001",
      "name": "FSDH Merchant Bank",
      "provider_type": "bank"
    },
    {
      "id": 2330,
      "code": "502",
      "name": "Rand merchant Bank",
      "provider_type": "bank"
    },
    {
      "id": 2331,
      "code": "608",
      "name": "FINATRUST MICROFINANCE BANK",
      "provider_type": "bank"
    },
    {
      "id": 2332,
      "code": "999001",
      "name": "CBN_TSA",
      "provider_type": "bank"
    },
    {
      "id": 2333,
      "code": "999999",
      "name": "NIP Virtual Bank",
      "provider_type": "bank"
    }
  ]
}