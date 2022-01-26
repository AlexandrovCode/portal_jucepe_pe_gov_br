import datetime
import hashlib
import json
import re

# from geopy import Nominatim

from src.bstsouecepkg.extract import Extract
from src.bstsouecepkg.extract import GetPages


class Handler(Extract, GetPages):
    base_url = 'https://portal.jucepe.pe.gov.br'
    NICK_NAME = base_url.split('//')[-1]
    fields = ['overview']
    overview = {}
    tree = None
    api = None

    header = {
        'User-Agent':
            'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0',
        'Accept':
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9;application/json',
        'accept-language': 'en-US,en;q=0.9,ru-RU;q=0.8,ru;q=0.7',
        'Content-Type': 'application/json'
    }

    def getResultListFromResponse(self, response, type):
        if type == 'API':
            data = json.loads(response.content)
            result = []
            try:
                companies = data['data'][1]['data']['rowData']
                for company in companies:
                    code = company['cellData'][1]['value']
                    # name = company['name'].replace(' ', '-')
                    # link = f'https://www.princeedwardisland.ca/en/feature/pei-business-corporate-registry-original#/service/LegacyBusiness/LegacyBusinessView;e=LegacyBusinessView;business_number={code}'
                    result.append(code)
                return result
            except:
                return None

    def getpages(self, searchquery):
        result = []
        url = 'https://portal.jucepe.pe.gov.br/async/empresas/publicas-mistas'
        self.get_working_tree_api(url, 'api')
        # print(self.api)
        for company in self.api:
            if searchquery in company['nome']:
                result.append(company)
        return result

    def get_by_xpath(self, xpath):
        try:
            el = self.tree.xpath(xpath)
        except Exception as e:
            print(e)
            return None
        if el:
            el = [i.strip() for i in el]
            el = [i for i in el if i != '']
            return el
        else:
            return None

    def reformat_date(self, date, format):
        date = datetime.datetime.strptime(date.strip(), format).strftime('%Y-%m-%d')
        return date

    def get_business_class(self, xpathCodes=None, xpathDesc=None, xpathLabels=None):
        res = []
        if xpathCodes:
            codes = self.get_by_xpath(xpathCodes)
        if xpathDesc:
            desc = self.get_by_xpath(xpathDesc)
        if xpathLabels:
            labels = self.get_by_xpath(xpathLabels)

        for c, d, l in zip(codes, desc, labels):
            temp = {
                'code': c.split(' (')[0],
                'description': d,
                'label': l.split('(')[-1].split(')')[0]
            }
            res.append(temp)
        if res:
            self.overview['bst:businessClassifier'] = res

    def get_post_addr(self, tree):
        addr = self.get_by_xpath(tree, '//span[@id="lblMailingAddress"]/..//text()', return_list=True)
        if addr:
            addr = [i for i in addr if
                    i != '' and i != 'Mailing Address:' and i != 'Inactive' and i != 'Registered Office outside NL:']
            if addr[0] == 'No address on file':
                return None
            if addr[0] == 'Same as Registered Office' or addr[0] == 'Same as Registered Office in NL':
                return 'Same'
            fullAddr = ', '.join(addr)
            temp = {
                'fullAddress': fullAddr if 'Canada' in fullAddr else (fullAddr + ' Canada'),
                'country': 'Canada',

            }
            replace = re.findall('[A-Z]{2},\sCanada,', temp['fullAddress'])
            if not replace:
                replace = re.findall('[A-Z]{2},\sCanada', temp['fullAddress'])
            if replace:
                torepl = replace[0].replace(',', '')
                temp['fullAddress'] = temp['fullAddress'].replace(replace[0], torepl)
            try:
                zip = re.findall('[A-Z]\d[A-Z]\s\d[A-Z]\d', fullAddr)
                if zip:
                    temp['zip'] = zip[0]
            except:
                pass
        # print(addr)
        # print(len(addr))
        if len(addr) == 4:
            temp['city'] = addr[-3]
            temp['streetAddress'] = addr[0]
        if len(addr) == 5:
            temp['city'] = addr[-4]
            temp['streetAddress'] = addr[0]
        if len(addr) == 6:
            temp['city'] = addr[-4]
            temp['streetAddress'] = ', '.join(addr[:2])

        return temp

    def get_address(self, xpath=None, zipPattern=None, key=None, returnAddress=False, addr=None):
        if xpath:
            addr = self.get_by_xpath(xpath)
        if key:
            addr = self.get_by_api(key)
        if addr:
            if '\n' in addr:
                splitted_addr = addr.split('\n')
            if ', ' in addr:
                splitted_addr = addr.split(', ')

            addr = addr.replace('\n', ' ')
            addr = addr[0] if type(addr) == list else addr
            temp = {
                'fullAddress': addr,
                'country': 'Brazil'
            }
            zip = re.findall(zipPattern, addr)
            if zip:
                temp['zip'] = zip[0]
            try:
                patterns = ['Suite\s\d+']
                for pattern in patterns:
                    pat = re.findall(pattern, addr)
                    if pat:
                        first_part = addr.split(pat[0])
                        temp['streetAddress'] = first_part[0] + pat[0]
            except:
                pass
            try:
                # city = addr.replace(temp['zip'], '')
                # city = city.replace(temp['streetAddress'], '')
                # city = city.replace(',', '').strip()
                # city = re.findall('[A-Z][a-z]+', city)
                temp['city'] = self.api['cidade']
                temp['fullAddress'] += f", {temp['city']}"
            except:
                pass
            temp['fullAddress'] += ', Brazil'
            if returnAddress:
                return temp
            self.overview['mdaas:RegisteredAddress'] = temp

    def get_prev_names(self, tree):
        prev = []
        names = self.get_by_xpath(tree,
                                  '//table[@id="tblPreviousCompanyNames"]//tr[@class="row"]//tr[@class="row"]//td[1]/text() | //table[@id="tblPreviousCompanyNames"]//tr[@class="row"]//tr[@class="rowalt"]//td[1]/text()',
                                  return_list=True)
        dates = self.get_by_xpath(tree,
                                  '//table[@id="tblPreviousCompanyNames"]//tr[@class="row"]//tr[@class="row"]//td[2]/span/text() | //table[@id="tblPreviousCompanyNames"]//tr[@class="row"]//tr[@class="rowalt"]//td[2]/span/text()',
                                  return_list=True)
        print(names)
        if names:
            names = [i for i in names if i != '']
        if names and dates:
            for name, date in zip(names, dates):
                temp = {
                    'name': name,
                    'valid_to': date
                }
                prev.append(temp)
        return prev

    def getFrombaseXpath(self, tree, baseXpath):
        pass

    def get_by_api(self, key):
        try:
            el = self.api[key]
            return el
        except:
            return None

    def fillField(self, fieldName, key=None, xpath=None, test=False, reformatDate=None):
        if xpath:
            el = self.get_by_xpath(xpath)
        if key:
            el = self.get_by_api(key)
        if test:
            print(el)
        if el:
            if fieldName == 'vcard:organization-name':
                self.overview[fieldName] = el.split('(')[0].strip()

            if fieldName == 'hasActivityStatus':
                self.overview[fieldName] = el

            if fieldName == 'bst:registrationId':
                el = f'{el[:2]}.{el[2:5]}.{el[5:8]}/{el[8:12]}-{el[12:]}'
                self.overview[fieldName] = el

            if fieldName == 'Service':
                self.overview[fieldName] = {'serviceType': el}

            if fieldName == 'regExpiryDate':
                self.overview[fieldName] = self.reformat_date(el, reformatDate) if reformatDate else el

            if fieldName == 'vcard:organization-tradename':
                self.overview[fieldName] = el.split('\n')[0].strip()

            if fieldName == 'bst:aka':
                names = el.split('\n')
                if len(names) > 1:
                    names = [i.strip() for i in names[1:]]
                    self.overview[fieldName] = names

            if fieldName == 'lei:legalForm':
                self.overview[fieldName] = {
                    'code': '',
                    'label': el}

            if fieldName == 'identifiers':
                el = f'{el[:2]}.{el[2:3]}.{el[3:10]}-{el[10:]}'
                self.overview[fieldName] = {
                    'other_company_id_number': el
                }
            if fieldName == 'map':
                self.overview[fieldName] = el[0] if type(el) == list else el

            if fieldName == 'previous_names':
                el = el.strip()
                el = el.split('\n')
                if len(el) < 1:
                    self.overview[fieldName] = {'name': [el[0].strip()]}
                else:
                    el = [i.strip() for i in el]
                    res = []
                    for i in el:
                        temp = {
                            'name': i
                        }
                        res.append(temp)
                    self.overview[fieldName] = res

            if fieldName == 'isIncorporatedIn':
                if reformatDate:
                    self.overview[fieldName] = self.reformat_date(el, reformatDate)
                else:
                    self.overview[fieldName] = el

            if fieldName == 'sourceDate':
                self.overview[fieldName] = self.reformat_date(el, '%d.%m.%Y')

            if fieldName == 'agent':
                # print(el)
                self.overview[fieldName] = {
                    'name': el.split('\n')[0],
                    'mdaas:RegisteredAddress': self.get_address(returnAddress=True, addr=' '.join(el.split('\n')[1:]),
                                                                zipPattern='[A-Z]\d[A-Z]\s\d[A-Z]\d')
                }
                # print(self.get_address(returnAddress=True, addr=' '.join(el.split('\n')[1:]),
                # zipPattern='[A-Z]\d[A-Z]\s\d[A-Z]\d'))

    def check_tree(self):
        print(self.tree.xpath('//text()'))

    def get_working_tree_api(self, link_name, type):
        if type == 'tree':
            self.tree = self.get_tree(link_name,
                                      headers=self.header)
        if type == 'api':
            self.api = self.get_content(link_name,
                                        headers=self.header)
            self.api = json.loads(self.api.content)
            self.api = self.api['sedes']

    def removeQuotes(self, text):
        text = text.replace('"', '')
        return text

    def get_overview(self, link_name):
        self.api = link_name
        # print(self.api)

        self.overview = {}

        try:
            self.fillField('vcard:organization-name', key='nome')
        except:
            return None

        self.overview['isDomiciledIn'] = 'BR'
        self.fillField('identifiers', key='nire')
        self.fillField('bst:registrationId', key='cnpj')
        self.overview['bst:sourceLinks'] = ['https://portal.jucepe.pe.gov.br/empresaspublicas']
        self.overview['regulator_name'] = 'the Commercial Board of the State of Pernambuco'
        self.overview['regulatorAddress'] = {
            'fullAddress': 'Rua Imperial, 1600 São José - Recife - PE CEP 50.090-000',
            'country': 'Brazil'
        }
        self.overview['RegulationStatus'] = 'Authorised'
        self.overview['bst:registryURI'] = 'https://portal.jucepe.pe.gov.br/empresaspublicas'
        self.overview['regulator_url'] = 'https://portal.jucepe.pe.gov.br'
        self.overview['@source-id'] = self.NICK_NAME
        self.get_address(key='endereco', zipPattern='\d\d\d\d+')

        # print(self.overview)
        # exit()
        # # self.overview['bst:sourceLinks'] = link_name
        #
        # self.fillField('vcard:organization-tradename', key='Trade Name(s)')
        # self.fillField('hasActivityStatus', key='Status')
        # self.fillField('bst:aka', key='Trade Name(s)')
        # self.fillField('previous_names', key='Former Name(s)')
        # self.fillField('lei:legalForm', key='Business Type')
        # self.fillField('isIncorporatedIn', key='Registration Date', reformatDate='%d-%b-%Y')
        #
        # self.fillField('Service', key='Business In')
        # self.fillField('agent', key='Chief Agent')
        # self.fillField('previous_names', key='Former Name(s)')
        # self.fillField('regExpiryDate', key='Expiry Date', reformatDate='%d-%b-%Y')
        # self.overview[
        #     'bst:registryURI'] = f'https://www.princeedwardisland.ca/en/feature/pei-business-corporate-registry-original#/service/LegacyBusiness/LegacyBusinessView;e=LegacyBusinessView;business_number={self.api["Registration Number"]}'
        # self.overview['@source-id'] = self.NICK_NAME


        # print(self.overview)
        # exit()
        # self.fillField('lei:legalForm', '//div/text()[contains(., "Legal form")]/../following-sibling::div//text()')
        # self.fillField('identifiers', '//div/text()[contains(., "Registry code")]/../following-sibling::div//text()')
        # self.fillField('map', '//div/text()[contains(., "Address")]/../following-sibling::div/a/@href')
        # self.fillField('incorporationDate', '//div/text()[contains(., "Registered")]/../following-sibling::div/text()')

        # self.fillField('bst:businessClassifier', '//div/text()[contains(., "EMTAK code")]/../following-sibling::div/text()')
        # self.get_business_class('//div/text()[contains(., "EMTAK code")]/../following-sibling::div/text()',
        #                         '//div/text()[contains(., "Area of activity")]/../following-sibling::div/text()',
        #                         '//div/text()[contains(., "EMTAK code")]/../following-sibling::div/text()')
        #
        # self.get_address('//div/text()[contains(., "Address")]/../following-sibling::div/text()',
        #                  zipPattern='\d{5}')
        #
        # self.overview['sourceDate'] = datetime.datetime.today().strftime('%Y-%m-%d')

        # self.overview['@source-id'] = self.NICK_NAME

        # print(self.overview)
        return self.overview

    def get_officership(self, link_name):
        self.get_working_tree_api(link_name, 'api')

        names = self.get_by_api('Officer(s)')
        if '\n' in names:
            names = names.split('\n')
        # roles = self.get_by_xpath(
        #     '//div/text()[contains(., "Right of representation")]/../following-sibling::div//tr/td[3]/text()')

        off = []
        names = [names] if type(names) == str else names
        roles = []
        for name in names:
            roles.append(name.split(' - ')[-1])
        names = [i.split(' - ')[0] for i in names]

        # roles = [roles] if type(roles) == str else roles
        for n, r in zip(names, roles):
            home = {'name': n,
                    'type': 'individual',
                    'officer_role': r,
                    'status': 'Active',
                    'occupation': r,
                    'information_source': self.base_url,
                    'information_provider': 'Prince Edward Island Corporate Registry'}
            off.append(home)
        return off

    # def get_documents(self, link_name):
    #     docs = []
    #     self.get_working_tree(link_name)
    #     docs_links = self.get_by_xpath('//div/a/text()[contains(., "PDF")]/../@href')
    #     docs_links = docs_links if type(docs_links) == list else [docs_links]
    #     docs_links = [f'{self.base_url}{i}' for i in docs_links]
    #     for doc in docs_links:
    #         temp = {
    #             'url': doc,
    #             'description': 'Summary of company details'
    #         }
    #         docs.append(temp)
    #     return docs

    # def get_financial_information(self, link_name):
    #     self.get_working_tree(link_name)
    #     fin = {}
    #     summ = self.get_by_xpath('//div/text()[contains(., "Capital")]/../following-sibling::div//text()')
    #     if summ:
    #         summ = re.findall('\d+', summ[0])
    #         if summ:
    #             fin['Summary_Financial_data'] = [{
    #                 'summary': {
    #                     'currency': 'Euro',
    #                     'balance_sheet': {
    #                         'authorized_share_capital': ''.join(summ)
    #                     }
    #                 }
    #             }]
    #     return fin
    def get_shareholders(self, link_name):

        edd = {}
        shareholders = {}
        sholdersl1 = {}

        company = self.get_overview(link_name)
        company_name_hash = hashlib.md5(company['vcard:organization-name'].encode('utf-8')).hexdigest()
        self.get_working_tree_api(link_name, 'api')
        # print(self.api)

        try:
            names = self.get_by_api('Shareholder(s)')
            if len(re.findall('\d+', names)) > 0:
                return edd, sholdersl1
            if '\n' in names:
                names = names.split('\n')

            holders = [names] if type(names) == str else names

            for i in range(len(holders)):
                holder_name_hash = hashlib.md5(holders[i].encode('utf-8')).hexdigest()
                shareholders[holder_name_hash] = {
                    "natureOfControl": "SHH",
                    "source": 'Prince Edward Island Corporate Registry',
                }
                basic_in = {
                    "vcard:organization-name": holders[i],
                    'isDomiciledIn': 'CA'
                }
                sholdersl1[holder_name_hash] = {
                    "basic": basic_in,
                    "shareholders": {}
                }
        except:
            pass

        edd[company_name_hash] = {
            "basic": company,
            "entity_type": "C",
            "shareholders": shareholders
        }
        # print(sholdersl1)
        return edd, sholdersl1
